#!/usr/bin/env python2
"""
Send SMS via Jasmin's HTTP API using 172.17.0.1:8080 as a DLR target
"""
import urllib2
import urllib

baseParams = {'username': 'testuser', 'password': 'testpass', 'to': '447428555555',
              'from': '447000111222', 'content': 'Hello',
              'dlr-url': 'http://172.17.0.1:8080/dlr', 'dlr-level': 3}

try:
    a = urllib2.urlopen("http://0.0.0.0:1401/send?%s" % urllib.urlencode(baseParams))
    print(a.read())
except Exception as err:
    print(err)
