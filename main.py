import twisted
from twisted.names import server, dns, client
from twisted.internet import reactor, defer
from twisted.internet.endpoints import TCP4ServerEndpoint
from twisted.protocols import portforward
import re


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
    def dataReceived(self, data):
        portforward.ProxyClient.dataReceived(self, data)

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
        print "==== Android Proxy Up and Running ===="


def main():
    print "DNS server will listen on localhost:65"
    print "HTTP Proxy will listen on localhost:8007"
    print "Start emulator using command: emulator @AvdName -http-proxy http://localhost:8007 -dns-server localhost"
    
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