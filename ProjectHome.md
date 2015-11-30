Background: http://www.mathyvanhoef.com/2013/06/transparent-interception-of-android.html

## What AndroidProxy does ##

This tool is designed to sit between the android emulator and your actuall proxy (Burp, WebScarab, Paros, etc). The goal is to enable you to easily intercept HTTPS traffic by sending the domain name (FQDN) to your actual proxy, instead of the IP adress. Your proxy is then able to create certificates for the correct domain name.

This is achieved by intercepting all DNS requests and rewriting the `CONNECT <ip>` command to `CONNECT <domain>` before it reaches your proxy. Normal HTTP traffic is left untouched. By intercepting all DNS request a unique IP address is associated with each domain (even if in reality the domains have the same IP). When an IP address is encountered in a CONNECT method we can lookup the unique IP address and find the corresponding domain name.

![http://i.imgur.com/pLX2V.png](http://i.imgur.com/pLX2V.png)

## The problem in detail ##

The emulator is essentially acts as an invisible proxy for HTTPS traffic, forwarding CONNECT request to the proxy you configured. These CONNECT commands are to the destination IP, hence the destination URL is lost. As a result your proxy generates a certificate with as common name the IP address of the server. If the client verifies the common name this will cause an error. Now, if the destination of the HTTPS request is always to the same domain, you could hardcode this domain in tools like Burp Suite ("generate a CA-signed certificate with a specific hostname"). However, if HTTPS requests are made to multiple domains, intercepting them becomes very troublesome (especially if multiple domains are hosted in the same IP). This script solves that problem by intercepting both DNS requests and HTTP(S) traffic.

![http://i.imgur.com/cRana.png](http://i.imgur.com/cRana.png)

The above screenshot, taken from the [wsec blog](http://www.wsec.be/blog/2011/10/05/adventures-in-pentesting-android-apps/), shows the invalid certificate warning that is displayed when you **don't** use the AndroidProxy.