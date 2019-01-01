import asyncio
import pytest
import logging
import socket
from contextlib import closing

from aiosmpp.config.httpapi import HTTPAPIConfig
from aiosmpp.config.smpp import SMPPConfig
from aiosmpp.smppmanager.server import SMPPManager, WebHandler as SMPPManagerWeb
from aiosmpp.httpapi.server import WebHandler as HTTPWeb


HTTPAPI_CONFIG = """[mq]
host = localhost
port = 1234
vhost = / 
user = guest
password = guest
heartbeat_interval = 30

[smpp_client]
url = http://localhost:8081

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
SMPP_CONFIG = """[mq]
host = localhost
port = 1234
vhost = / 
user = guest
password = guest
heartbeat_interval = 30

[smpp_bind:smpp_conn1]
host = 127.0.10.1
port = 2775
bind_type = TRX
ssl = no

systemid = test1
password = testpw
src_ton = 1
src_npi = 1
dst_ton = 1
dst_npi = 1
bind_ton = 0
bind_npi = 1
priority = 0
requeue_delay = 120
dlr_expiry = 86400
submit_throughput = 50
coding = 0
enquire_link_interval = 30
replace_if_present_flag = 0
dlr_msgid = 0
disabled = 0
"""


@pytest.fixture
def free_port():
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(('', 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


@pytest.fixture
def smpp_config(rabbitmq_container, redis_container, dlr_mo_server_1, dlr_mo_server_2, dlr_mo_server_3):
    config = SMPPConfig.from_file(config=SMPP_CONFIG)

    # Copy the config to additional smpp connections
    config.connectors['smpp_conn2'] = config.connectors['smpp_conn1'].copy()
    config.connectors['smpp_conn3'] = config.connectors['smpp_conn1'].copy()

    # Change host/port to match random ones
    config.connectors['smpp_conn1']['host'] = dlr_mo_server_1[0]
    config.connectors['smpp_conn1']['port'] = str(dlr_mo_server_1[1])
    config.connectors['smpp_conn2']['host'] = dlr_mo_server_2[0]
    config.connectors['smpp_conn2']['port'] = str(dlr_mo_server_2[1])
    config.connectors['smpp_conn3']['host'] = dlr_mo_server_3[0]
    config.connectors['smpp_conn3']['port'] = str(dlr_mo_server_3[1])

    # Adjust port to match container random ports
    config.mq['port'] = rabbitmq_container.ports['5672/tcp'][0]
    config.redis['port'] = redis_container.ports['6379/tcp'][0]

    return config


@pytest.fixture
async def smpp_management_server(smpp_config, free_port, aiohttp_server):
    logger = logging.getLogger()
    smpp_manager = SMPPManager(config=smpp_config, logger=logger)
    web_server = SMPPManagerWeb(smpp_manager=smpp_manager, config=smpp_config, logger=logger)

    server = await aiohttp_server(web_server.app())
    yield server

    # Call close as otherwise it calls the close when the event loop is torn down :/
    await server.close()


@pytest.fixture
def httpapi_config(rabbitmq_container):
    config = HTTPAPIConfig.from_file(config=HTTPAPI_CONFIG)

    config.mq['port'] = rabbitmq_container.ports['5672/tcp'][0]

    return config


@pytest.fixture
async def http_api_server(httpapi_config, smpp_management_server, aiohttp_client):
    logger = logging.getLogger()
    httpapi_config.smpp_client_url = 'http://localhost:' + str(smpp_management_server.port)

    web_server = HTTPWeb(config=httpapi_config, logger=logger)

    client = await aiohttp_client(web_server.app())
    yield web_server, client

    # Call close as otherwise it calls the close when the event loop is torn down :/
    await client.close()
