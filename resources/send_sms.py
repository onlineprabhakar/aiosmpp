#!/usr/bin/env python2
import urllib2
import urllib

baseParams = {'username':'testuser', 'password':'testpass', 'to':'447428555555', 'from': '447000111222', 'content':'Hello'}

try:
    a = urllib2.urlopen("http://0.0.0.0:1401/send?%s" % urllib.urlencode(baseParams))
    print(a.read())
except Exception as err:
    print(err)
