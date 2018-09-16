=======
aiosmpp
=======

.. image:: https://img.shields.io/pypi/v/aiosmpp.svg
        :target: https://pypi.python.org/pypi/aiosmpp

.. image:: https://img.shields.io/travis/terrycain/aiosmpp.svg
        :target: https://travis-ci.org/terrycain/aiosmpp

.. image:: https://readthedocs.org/projects/aiosmpp/badge/?version=latest
        :target: https://aiosmpp.readthedocs.io
        :alt: Documentation Status

.. image:: https://pyup.io/repos/github/terrycain/aiosmpp/shield.svg
     :target: https://pyup.io/repos/github/terrycain/aiosmpp/
     :alt: Updates

Why
---

Well the main reason is I like async python and relative boredom. The main aim for this project is to provide a more
cloud-native SMPP framework similar to the excellent Jasmin SMS gateway project (jasmin_). I really liked
how that worked but one of the main irks I had with it was the config and overall management, so I thought, how hard can it be to re-invent the wheel.
We shall see.

To make a decent SMPP framework and to get an in-depth knowledge I thought I'd look into making a quick and simple SMPP server
implementation. Its nearly at the point where I'm happy with it, and am using a customised version server part internally in production
(not for anything heavy might I add).

I'd say on a whole this project is in its pre-alpha stages.

The overall architecture is near enough the same as the Jasmin project has, though slimmed down and for now, only doing what I want it to.

Config will be stored in a text file (or Dynamo, I'm an AWS fan). All parts are designed eventually to be in their own containers 
and to cope with multiple running. You have the smpp client container, this deals with sending and receiving smpp PDUs (or putting it simply, SMS).
Then you have a HTTP API, which will also do basic routing (go look at jasmin docs for that). An interceptor container (again jasmin docs) which can
do some manipulation of SMPP PDUs. And then some misc containers to deal with delivery notifications and inbound sms. All using RabbitMQ.

Currently working
-----------------

- basic smpp client, though its not very user friendly yet
- simple smpp server

TODO
----

- Proper server docs
- Get main framework in a useable and deployable state

As this is currently in a pre-alpha like stage, stuff will change at will until I'm happy with it. So if for some 
weird reason someone than other than me is using this, you've been warned. Other than that, I've probably got some of this wrong, so raise issues.

.. _jasmin: https://github.com/jookies/jasmin
