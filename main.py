# TODO's:
# - Script currently doesn't treat TCP connections a streamed data. Normally we should buffer input
#   untill enough data has been received and then do our checks. However since the connections are
#   local all data is received at once (most of the time) so this code does work :)
import twisted
from twisted.names import server, dns, client
from twisted.internet import reactor, defer
from twisted.internet.endpoints import TCP4ServerEndpoint
from twisted.protocols import portforward
import re
from socket import *
import struct

# symbolic definition of getsockopt parameter
SO_ORIGINAL_DST = 80

# Mapping of domain name to given unique IP
mappings = dict()
# Mapping of given unique IP to domain name
reversemappings = dict()


# --------------------------------------- DNS SERVER ---------------------------------------


# Custom DNS server which assigns a unique IP address to every domain, even if
# in reality two domains share the same IP.
class ProxyResolver(client.Resolver):

	# Start with IP 1.1.1.1
	def __init__(self, servers):
		client.Resolver.__init__(self, servers=servers)
		self.ttl = 10
		self.ip = [1, 1, 1, 1]

	# Helper function: Move to next IP and return it as a string
	def nextIp(self):
		self.ip[3] += 1
		for i in range(3,1,-1):
			if (self.ip[i] == 255):
				self.ip[i] = 1
				self.ip[i-1] += 1
		return str(self.ip[0]) + "." + str(self.ip[1]) + "." +str(self.ip[2]) + "." +str(self.ip[3])

	def lookupAddress(self, name, timeout = None):
		# If it's the first time a DNS lookup is done for this domain, assign it
		# a unique IP and update the mappings
		if (not mappings.has_key(name)):
			ip = self.nextIp()
			mappings[name] = ip
			reversemappings[str(self.ip[0]) + "." + str(self.ip[1]) + "." +str(self.ip[2]) + "." +str(self.ip[3])] = name
		
		# Get the mapped IP!
		ip = mappings[name]
		print "DNS:", name, "->", ip
		
		# From the manual: "Defer is useful when you're writing synchronous code to an asynchronous
		# interface: i.e., some code is calling you expecting a Deferred result, but you don't actually
		# need to do anything asynchronous. Just return defer.succeed(theResult)."
		return defer.succeed([(dns.RRHeader(name, dns.A, dns.IN, self.ttl, dns.Record_A(ip, self.ttl)),), (), ()])


# --------------------------------------- HTTP PROXY ---------------------------------------


# Communication between your actual proxy (Burp, WebScarab, ..) and our script.
class ProxyClient(portforward.ProxyClient):
	def __init__(self):
		self.gotestablished = False
		self.requestdata = None

	def setRequestData(self, data):
		self.requestdata = data

	def dataReceived(self, data):
		# TODO: How does this work when proxying a real device?! Connect shouldn't be sent then?!
		if self.gotestablished or self.requestdata == None:
			# If the connection has been established just forward the data to the emulator
			# TODO: Check this
			portforward.ProxyClient.dataReceived(self, data)
		else:
			# TODO: Check this
			if not "HTTP/1.0 200 Connection established\r\n\r\n" in data:
				print "Warning: Unexpected proxy reply:", repr(data[:30])
			else:
				print "Proxy CONNECT reply: >", repr(data[:30])

			self.gotestablished = True
			# Forward data to Android
			self.transport.write(self.requestdata)


# TODO: Check this
class ProxyClientFactory(portforward.ProxyClientFactory):
	protocol = ProxyClient


# Custom HTTP proxy. Intercepts the CONNECT <ip> command, looks up the corresponding domain name, and
# forwards the correct CONNECT <domain> command to your actual proxy.
class ProxyServer(portforward.ProxyServer):
	clientProtocolFactory = ProxyClientFactory

	def __init__(self):
		self.receivedfirst = False
		self.connectre = re.compile(r'CONNECT (\d+\.\d+\.\d+\.\d+):\d+ HTTP')
		self.otherre = re.compile(r'\w+ http://(\d+\.\d+\.\d+\.\d+)')
		self.firstdata = None


	def dataReceived(self, data):
		# The first time we recieve data we must check for invisible proxiying and rewrite
		# the CONNECT/GET requests to use the actual domain name.
		if not self.receivedfirst:
			print "INCOMING TCP CONN: >", repr(data.split("\r")[0][:40])

			# Of course invisible proxying is unnecessairy if the CONNECT command is actually used!
			
			# ------------------------- Invisible Proxying Support ---------------------------
			
			# TODO: This is UNTESTED and EXPERIMENTAL code
			"""
			
			# TODO: Get ourselves an Android VMWare image and test this :)
			# Only do invisible proxifying if there is no CONNECT command
			# TODO: We should actually check if it *START* with CONNECT
			if not "CONNECT" in data:
			
				# We support invisible proxying for real Android devicec, where the computer is configured
				# as the router, and all HTTP(S) traffic is redirected to our tool. In this scenario we
				# don't receive a CONNECT request. Instead we get the original destination IP address and
				# manually construct the CONNECT request.
				
				# TODO: Test this on other operating systems than Linux
				try:
					# Ask the OS the original destination of the connection
					dst = socket.getsockopt(self.transport.socket, SOL_IP, SO_ORIGINAL_DST, 16)
					# Exclamation mark tells unpack that dst is big-endian
					# 2x  : two pad bytes
					# H   : unsigned short (port)
					# 4s  : char string of 4 bytes (ip)
					# 8x  : eight pad bytes
					srv_port, srv_ip = struct.unpack("!2xH4s8x", dst)

					if srv_port == 443:
						self.peer.setRequestData(data)
						data = "CONNECT " + inet_ntoa(srv_ip) + ":" + str(srv_port) + " HTTP/1.1\r\n\r\n"
						print "PROXIFYING HTTPS: " + repr(data.strip())
					# NOTE: If you uncomment this elif block, your proxy must support invisible proxying
					elif srv_port == 80:
						# Rewrite to absolute GET request if info available
						if reversemappings.has_key(inet_ntoa(srv_ip)):
							data = re.sub(r'^GET ', "GET http://" + reversemappings[inet_ntoa(srv_ip)] + ":" + str(srv_port), data)
						else:
							print "Warning: got redirected HTTP request but unable to find destination hostname:port"
				
				except Exception, e:
					print "Something went wrong with invisible proxying:", e.getMessage()
			"""
			
			# ------------------- Rewrite CONNECT/GET/POST with domain name ---------------------
			
			resultconnect = self.connectre.match(data)
			resultother = self.otherre.match(data)
			
			# TODO: We shouldn't use a normal replace after using regular expressions..
			# Replace IP in CONNECT
			if (resultconnect != None and reversemappings.has_key(resultconnect.group(1))):
				data = data.replace(resultconnect.group(1), reversemappings[resultconnect.group(1)])
				print "REWRITING CONNECT:", resultconnect.group(1), "->", reversemappings[resultconnect.group(1)]
			# Replace IP in GET, POST, HEAD, etc
			elif (resultother != None and reversemappings.has_key(resultother.group(1))):
				data = data.replace(resultother.group(1), reversemappings[resultother.group(1)])
				print "REWRITING HTTP METHOD:", resultother.group(1), "->", reversemappings[resultother.group(1)]
			
			self.firstdata = data
			self.receivedfirst = True
			
			print "OUTGOING TCP: >", repr(data.split("\r")[0][:40])
		
		
		# forward data
		portforward.ProxyServer.dataReceived(self, data)
	


class ProxyFactory(portforward.ProxyFactory):
	protocol = ProxyServer
	
	def doStart(self):
		print "\t==== Android Proxy Up and Running ====\n"


def main():
	print "AndroidProxy   ---   (C) Mathy Vanhoef"
	print "This program comes with ABSOLUTELY NO WARRANTY."
	print
	print "DNS server will listen on localhost:53"
	print "HTTP Proxy will listen on localhost:8007"
	print
	#print "Physical device: Configure your computer dns server and as router (NOT as proxy) and execute"
	#print "\tiptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to-port 8007"
	#print "\tiptables -t nat -A PREROUTING -p tcp --dport 443 -j REDIRECT --to-port 8007"
	#print
	print "Emulator: start it using: emulator @AvdName -http-proxy http://localhost:8007 -dns-server localhost"
	print
	print "Don't forget to start your normal proxy on localhost:8080"
	print
	
	# Setup custom DNS server
	resolvers = []
	resolvers.append(ProxyResolver([('8.8.8.8', 53)]))
	f = server.DNSServerFactory(clients=resolvers)
	p = dns.DNSDatagramProtocol(f)
	reactor.listenUDP(53, p)
	
	# Setup TCP proxy server
	endpoint = TCP4ServerEndpoint(reactor, 8007)
	endpoint.listen(ProxyFactory('localhost', 8080))

	# Start DNS and TCP server
	reactor.run();


if __name__ == "__main__":
	main()

