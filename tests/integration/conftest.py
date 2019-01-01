import asyncio
import pytest
import logging
import socket
import threading
from contextlib import closing

from aiosmpp.server import RawSMPPServer
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
def smpp_config_mtonly(rabbitmq_container, redis_container, mt_server_1, mt_server_2, mt_server_3):
    config = SMPPConfig.from_file(config=SMPP_CONFIG)

    # Copy the config to additional smpp connections
    config.connectors['smpp_conn2'] = config.connectors['smpp_conn1'].copy()
    config.connectors['smpp_conn3'] = config.connectors['smpp_conn1'].copy()

    # Change host/port to match random ones
    config.connectors['smpp_conn1']['host'] = mt_server_1[0]
    config.connectors['smpp_conn1']['port'] = str(mt_server_1[1])
    config.connectors['smpp_conn2']['host'] = mt_server_2[0]
    config.connectors['smpp_conn2']['port'] = str(mt_server_2[1])
    config.connectors['smpp_conn3']['host'] = mt_server_3[0]
    config.connectors['smpp_conn3']['port'] = str(mt_server_3[1])

    # Adjust port to match container random ports
    config.mq['port'] = rabbitmq_container.ports['5672/tcp'][0]
    config.redis['port'] = redis_container.ports['6379/tcp'][0]

    return config


@pytest.fixture
async def smpp_management_server_mtonly(smpp_config_mtonly, free_port, aiohttp_server):
    logger = logging.getLogger()
    smpp_manager = SMPPManager(config=smpp_config_mtonly, logger=logger)
    web_server = SMPPManagerWeb(smpp_manager=smpp_manager, config=smpp_config_mtonly, logger=logger)

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
async def http_api_server(httpapi_config, aiohttp_server, smpp_management_server_mtonly):
    logger = logging.getLogger()
    httpapi_config.smpp_client_url = 'http://localhost:' + str(smpp_management_server_mtonly.port)  # '8081'

    web_server = HTTPWeb(config=httpapi_config, logger=logger)

    client = await aiohttp_server(web_server.app())
    base_url = 'http://{0}:{1}/'.format(client.host, client.port)

    yield web_server, client, base_url

    await client.close()


class SimpleReceiveServer(RawSMPPServer):
    def __init__(self, *args, test_mt_list, **kwargs):
        super(SimpleReceiveServer, self).__init__(*args, **kwargs)

        self.test_mt_list = test_mt_list

    def handle_submit_sm(self, request) -> str:
        # Get msg id, from calling the method of the superclass (also does logging)
        msg_id = super(SimpleReceiveServer, self).handle_submit_sm(request)

        # Return MSG ID, this'll go in the submit sm
        return msg_id


def smpp_server_thread(local_ip: str, port: int, shared_list: list, threading_event: threading.Event):
    try:
        logger = logging.getLogger()

        loop = asyncio.new_event_loop()
        # were in a different thread so set default loop
        asyncio.set_event_loop(loop)

        # Loop round so that when threading event is set, run_forever will stop
        async def _close_loop():
            while True:
                if threading_event.is_set():
                    loop.close()
                    break
                await asyncio.sleep(0.01, loop=loop)

        asyncio.ensure_future(_close_loop(), loop=loop)

        server_coro = loop.create_server(lambda: SimpleReceiveServer(logger=logger, test_mt_list=shared_list), local_ip, port)
        server = loop.run_until_complete(server_coro)

        # Serve requests until Ctrl+C is pressed
        logger.info('Serving on {0[0]}:{0[1]}'.format(server.sockets[0].getsockname()))

        loop.run_forever()

        server.close()
        loop.run_until_complete(server.wait_closed())
        loop.close()
    except Exception as err:
        raise err




@pytest.fixture
async def mt_server_1():
    address, port = '127.0.10.1', 2775
    logger = logging.getLogger()

    loop = asyncio.get_event_loop()


    mt_list = []
    server_coro = loop.create_server(lambda: SimpleReceiveServer(logger=logger, test_mt_list=mt_list), address, port)
    server = await server_coro

    # Serve requests until Ctrl+C is pressed
    logger.info('Serving on {0[0]}:{0[1]}'.format(server.sockets[0].getsockname()))

    yield address, port, mt_list

    # Close the server
    server.close()
    await server.wait_closed()


@pytest.fixture
async def mt_server_2():
    address, port = '127.0.10.2', 2775
    logger = logging.getLogger()

    mt_list = []
    server_coro = asyncio.get_event_loop().create_server(lambda: SimpleReceiveServer(logger=logger, test_mt_list=mt_list), address, port)
    server = await server_coro

    # Serve requests until Ctrl+C is pressed
    logger.info('Serving on {0[0]}:{0[1]}'.format(server.sockets[0].getsockname()))

    yield address, port, server

    # Close the server
    server.close()
    await server.wait_closed()


@pytest.fixture
async def mt_server_3():
    address, port = '127.0.10.3', 2775
    logger = logging.getLogger()

    mt_list = []
    server_coro = asyncio.get_event_loop().create_server(lambda: SimpleReceiveServer(logger=logger, test_mt_list=mt_list), address, port)
    server = await server_coro

    # Serve requests until Ctrl+C is pressed
    logger.info('Serving on {0[0]}:{0[1]}'.format(server.sockets[0].getsockname()))

    yield address, port, server

    # Close the server
    server.close()
    await server.wait_closed()
