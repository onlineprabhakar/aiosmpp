import pytest

from aiosmpp.config.httpapi import HTTPAPIConfig


HTTPAPI_CONFIG = """[mq]
host = localhost
port = 1234
# vhost = 
# user = user
# password = passwd
heartbeat_interval = 30

[somerandomsection]
test = 1

[mt_route:20]
type = static
connector = smpp_conn3
filters = tag_filter1

[mt_route:10]
type = static
connector = smpp_conn2
filters = uk_addr,tag_filter2

[mt_route:0]
type = default
connector = smpp_conn1

[mo_route:0]
type = default
url = http://example.org/test.php

[filter:tag_filter1]
type = tag
tag = 1337

[filter:tag_filter2]
type = tag
tag = 666

[filter:uk_addr]
type = destaddr
regex = ^44.+
"""


@pytest.fixture
def httpapi_config(rabbitmq_container, dlr_mo_server_1):
    config = HTTPAPIConfig.from_file(config=HTTPAPI_CONFIG)

    config.mq['port'] = rabbitmq_container.ports['5672/tcp'][0]

    return config
