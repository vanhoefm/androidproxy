import twisted
from twisted.names import server, dns, client
from twisted.internet import reactor, defer
from twisted.internet.endpoints import TCP4ServerEndpoint
from twisted.protocols import portforward
import re
from socket import *
import struct

# getsockopt parameter
SO_ORIGINAL_DST = 80

mappings = dict()
reversemappings = dict()


class ProxyResolver(client.Resolver):

    def __init__(self, servers):
        client.Resolver.__init__(self, servers=servers)
        self.ttl = 10
        self.ip = [1, 1, 1, 1]

    def nextIp(self):
        self.ip[3] += 1
        for i in range(3,1,-1):
            if (self.ip[i] == 255):
                self.ip[i] = 1
                self.ip[i-1] += 1
        return str(self.ip[0]) + "." + str(self.ip[1]) + "." +str(self.ip[2]) + "." +str(self.ip[3])

    def lookupAddress(self, name, timeout = None):
        if (not mappings.has_key(name)):
            ip = self.nextIp()
            mappings[name] = ip
            reversemappings[str(self.ip[0]) + "." + str(self.ip[1]) + "." +str(self.ip[2]) + "." +str(self.ip[3])] = name
        
        ip = mappings[name]
        print "DNS:", name, "->", ip
        # Defer is useful when you're writing synchronous code to an asynchronous interface: i.e., some code is calling
        # you expecting a Deferred result, but you don't actually need to do anything asynchronous. Just return defer.succeed(theResult).
        return defer.succeed([(dns.RRHeader(name, dns.A, dns.IN, self.ttl, dns.Record_A(ip, self.ttl)),), (), ()])



class ProxyClient(portforward.ProxyClient):
    def __init__(self):
        self.gotestablished = False
        self.requestdata = None

    def setRequestData(self, data):
        self.requestdata = data

    def dataReceived(self, data):
        if self.gotestablished or self.requestdata == None:
            # Forward traffic to the client
            portforward.ProxyClient.dataReceived(self, data)
        else:
            # TODO: Verify that received data is indeed "HTTP/1.0 200 Connection established"
            self.gotestablished = True
            # Send original HTTPS request
            self.transport.write(self.requestdata)


class ProxyClientFactory(portforward.ProxyClientFactory):
    protocol = ProxyClient



class ProxyServer(portforward.ProxyServer):
    clientProtocolFactory = ProxyClientFactory

    def __init__(self):
        self.receivedfirst = False
        self.headerre = re.compile(r'CONNECT (\d+\.\d+\.\d+\.\d+):\d+ HTTP')
        self.firstdata = None


    def dataReceived(self, data):
        if not self.receivedfirst:

            dst = socket.getsockopt(self.transport.socket, SOL_IP, SO_ORIGINAL_DST, 16)
            srv_port, srv_ip = struct.unpack("!2xH4s8x", dst)

            #TODO: Find better way to detect redirected traffic. Now we assume only HTTPS needs conversion.
            if srv_port == 443:
                # We assume redirect traffic is not yet proxied, so add CONNECT command
                self.peer.setRequestData(data)
                data = "CONNECT " + inet_ntoa(srv_ip) + ":" + str(srv_port) + " HTTP/1.1\r\n\r\n"
            # NOTE: If you uncomment this elif block, your proxy must support invisible proxying
            elif srv_port == 80:
                # Rewrite to absolute GET request if info available
		if reversemappings.has_key(inet_ntoa(srv_ip)):
                    data = re.sub(r'^GET ', "GET http://" + reversemappings[inet_ntoa(srv_ip)] + ":" + str(srv_port), data)
            
            result = self.headerre.match(data)

            if (result != None and reversemappings.has_key(result.group(1))):
                data = data.replace(result.group(1), reversemappings[result.group(1)])
                print "PROXY:", result.group(1), "->", reversemappings[result.group(1)]
            
            self.firstdata = data
            self.receivedfirst = True
        
        # forward data
        portforward.ProxyServer.dataReceived(self, data)
    


class ProxyFactory(portforward.ProxyFactory):
    protocol = ProxyServer
    
    def doStart(self):
        print "\t==== Android Proxy Up and Running ====\n"


def main():
    print "AndroidProxy  ---   (C) Mathy Vanhoef (Made While Intern @ Ernst & Young)"
    print "This program comes with ABSOLUTELY NO WARRANTY."
    print
    print "DNS server will listen on localhost:65"
    print "HTTP Proxy will listen on localhost:8007"
    print
    print "Physical device: Configure your computer as router and dns server and execute"
    print "\tiptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to-port 8007"
    print "\tiptables -t nat -A PREROUTING -p tcp --dport 443 -j REDIRECT --to-port 8007"
    print
    print "Start emulator using command: emulator @AvdName -http-proxy http://localhost:8007 -dns-server localhost"
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
    '(http://)?(\s+):(\d+)'
    main()

