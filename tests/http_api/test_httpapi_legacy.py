import binascii
import asyncio
import json

import pytest

import multidict
from aiosmpp.config.httpapi import HTTPAPIConfig
from aiosmpp.httpapi.server import WebHandler
from aiosmpp.smppmanager.client import SMPPManagerClient


HTTPAPI_CONFIG = """[mq]
host = test
port = 1234
vhost = example
user = user
password = passwd
heartbeat_interval = 1

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


class AMQPMock(object):
    class AMQPTransport(object):
        pass

    class AMQPChannel(object):
        def __init__(self):
            self.calls = []

        async def basic_publish(self, payload, exchange_name, routing_key):
            self.calls.append({'payload': payload, 'exchange_name': exchange_name, 'routing_key': routing_key})

    def __init__(self):
        self.init_args = None
        self.channels = []

    async def __call__(self, *args, **kwargs):
        self.init_args = args, kwargs

        return self.AMQPTransport, self

    async def channel(self):
        new_channel = self.AMQPChannel()
        self.channels.append(new_channel)

        return new_channel


SMPP_CLIENT_RESPONSE = {
    "connectors": {
        "smpp_conn1": {
            "state": "BOUND_TRX",
            "config": {
                "connector_name": "smpp_conn1",
                "host": "127.0.10.1",
                "port": 2775,
                "bind_type": "TRX",
                "ssl": False,
                "systemid": "test1",
                "password": "testpw",
                "conn_loss_retry": True,
                "conn_loss_delay": 30,
                "priority_flag": 0,
                "submit_throughput": 50,
                "coding": 0,
                "enquire_link_interval": 30,
                "replace_if_present_flag": 0,
                "protocol_id": None,
                "validity_period": None,
                "service_type": None,
                "addr_range": None,
                "source_addr_ton": 1,
                "source_addr_npi": 1,
                "dest_addr_ton": 1,
                "dest_addr_npi": 1,
                "bind_ton": 0,
                "bind_npi": 1,
                "sm_default_msg_id": 0,
                "dlr_msgid": 0,
                "dlr_expiry": 86400,
                "requeue_delay": 120,
                "queue_name": "smpp_smpp_conn1",
                "dlr_queue_name": "dlr",
                "mo_queue_name": "mo",
                "mq": {
                    "host": "127.0.0.1",
                    "port": 5672,
                    "vhost": "/",
                    "user": "guest",
                    "password": "guest",
                    "heartbeat_interval": 30
                }
            }
        }
    }
}


class SMPPClientManager(SMPPManagerClient):
    def __init__(self, *args, **kwargs):
        super(SMPPClientManager, self).__init__(*args, **kwargs)
        self.connectors = SMPP_CLIENT_RESPONSE

    async def close(self):
        pass

    async def run(self, interval: int = 120):
        try:
            while True:
                await asyncio.sleep(0.2)
        except:
            pass


def get_app():
    config = HTTPAPIConfig.from_file(config=HTTPAPI_CONFIG)
    mock = AMQPMock()
    handler = WebHandler(config=config, amqp_connect=mock, smppmanagerclientclass=SMPPClientManager)

    return mock, handler


async def test_legacy_missing_param(aiohttp_client):
    amqp_mock, handler = get_app()
    client = await aiohttp_client(handler.app())

    # Wont match smpp conn 2 or 3, so should be smpp_conn1
    payload = {
        'content': '£ test',
        'to': '447428555555',
        'from': '447428666666',
        'coding': '0'
    }

    resp = await client.get('/send', params=payload)
    assert resp.status == 400
    text = await resp.text()
    assert 'Error "' in text


async def test_legacy_no_route(aiohttp_client):
    amqp_mock, handler = get_app()
    client = await aiohttp_client(handler.app())

    # Wont match smpp conn 2 or 3, so should be smpp_conn1
    payload = {
        'content': '£ test',
        'to': '447428555555',
        'from': '447428666666',
        'username': 'test',
        'password': 'test',
        'coding': '0',
        'tags': '1337'
    }

    resp = await client.get('/send', params=payload)
    assert resp.status == 412
    text = await resp.text()
    assert text == 'Error "No route found"'


async def test_legacy_send_gsm7(aiohttp_client):
    amqp_mock, handler = get_app()
    client = await aiohttp_client(handler.app())

    # Wont match smpp conn 2 or 3, so should be smpp_conn1
    payload = {
        'content': '£ test',
        'to': '447428555555',
        'from': '447428666666',
        'username': 'test',
        'password': 'test',
        'coding': '0'
    }

    resp = await client.get('/send', params=payload)
    assert resp.status == 200
    text = await resp.text()  # should look like 'Success "random-uuid"'

    assert amqp_mock.channels
    amqp_channel = amqp_mock.channels[0]
    assert amqp_channel.calls
    call = amqp_channel.calls[0]

    # Check amqp data
    amqp_payload = json.loads(call['payload'])
    assert call['routing_key'] == 'smpp_smpp_conn1'
    assert call['exchange_name'] == ''

    assert 'Success "{0}"'.format(amqp_payload['req_id']) in text

    assert amqp_payload['connector'] == 'smpp_conn1'
    assert len(amqp_payload['pdus']) == 1

    pdu = amqp_payload['pdus'][0]
    # Spot check some pdu values
    assert pdu['source_addr'] == '447428666666'
    assert pdu['destination_addr'] == '447428555555'
    assert pdu['data_coding'] == 0
    assert pdu['short_message'] == '\x01 test'
    assert pdu['sm_default_msg_id'] == 0


async def test_legacy_send_latin1(aiohttp_client):
    amqp_mock, handler = get_app()
    client = await aiohttp_client(handler.app())

    # Wont match smpp conn 2 or 3, so should be smpp_conn1
    payload = {
        'content': '£ test',
        'to': '447428555555',
        'from': '447428666666',
        'username': 'test',
        'password': 'test',
        'coding': '3'
    }

    resp = await client.get('/send', params=payload)
    assert resp.status == 200
    text = await resp.text()  # should look like 'Success "random-uuid"'

    assert amqp_mock.channels
    amqp_channel = amqp_mock.channels[0]
    assert amqp_channel.calls
    call = amqp_channel.calls[0]

    # Check amqp data
    amqp_payload = json.loads(call['payload'])
    assert call['routing_key'] == 'smpp_smpp_conn1'
    assert call['exchange_name'] == ''

    assert 'Success "{0}"'.format(amqp_payload['req_id']) in text

    assert amqp_payload['connector'] == 'smpp_conn1'
    assert len(amqp_payload['pdus']) == 1

    pdu = amqp_payload['pdus'][0]
    # Spot check some pdu values
    assert pdu['source_addr'] == '447428666666'
    assert pdu['destination_addr'] == '447428555555'
    assert pdu['data_coding'] == 3
    assert pdu['short_message'] == '£ test'
    assert pdu['sm_default_msg_id'] == 0


async def test_legacy_send_ucs2(aiohttp_client):
    amqp_mock, handler = get_app()
    client = await aiohttp_client(handler.app())

    # Wont match smpp conn 2 or 3, so should be smpp_conn1
    content = binascii.hexlify('£ test'.encode('utf-16-be')).decode()

    payload = {
        'hex-content': content,
        'to': '447428555555',
        'from': '447428666666',
        'username': 'test',
        'password': 'test',
        'coding': '8'
    }

    resp = await client.get('/send', params=payload)
    assert resp.status == 200
    text = await resp.text()  # should look like 'Success "random-uuid"'

    assert amqp_mock.channels
    amqp_channel = amqp_mock.channels[0]
    assert amqp_channel.calls
    call = amqp_channel.calls[0]

    # Check amqp data
    amqp_payload = json.loads(call['payload'])
    assert call['routing_key'] == 'smpp_smpp_conn1'
    assert call['exchange_name'] == ''

    assert 'Success "{0}"'.format(amqp_payload['req_id']) in text

    assert amqp_payload['connector'] == 'smpp_conn1'
    assert len(amqp_payload['pdus']) == 1

    pdu = amqp_payload['pdus'][0]
    # Spot check some pdu values
    assert pdu['source_addr'] == '447428666666'
    assert pdu['destination_addr'] == '447428555555'
    assert pdu['data_coding'] == 8
    assert pdu['short_message_hex'] == content
    assert pdu['sm_default_msg_id'] == 0


async def test_legacy_send_gsm7_long(aiohttp_client):
    amqp_mock, handler = get_app()
    client = await aiohttp_client(handler.app())

    # Wont match smpp conn 2 or 3, so should be smpp_conn1
    payload = {
        'content': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit. Donec vel sagittis tortor. Maecenas eu tempor neque. '
                   'Aliquam erat volutpat. Donec tincidunt, nisl pharetra condimentum pellentesque, justo sed.',
        'to': '447428555555',
        'from': '447428666666',
        'username': 'test',
        'password': 'test',
        'coding': '0'
    }

    resp = await client.get('/send', params=payload)
    assert resp.status == 200
    text = await resp.text()  # should look like 'Success "random-uuid"'

    assert amqp_mock.channels
    amqp_channel = amqp_mock.channels[0]
    assert amqp_channel.calls
    call = amqp_channel.calls[0]

    # Check amqp data
    amqp_payload = json.loads(call['payload'])
    assert call['routing_key'] == 'smpp_smpp_conn1'
    assert call['exchange_name'] == ''

    assert 'Success "{0}"'.format(amqp_payload['req_id']) in text

    assert amqp_payload['connector'] == 'smpp_conn1'
    assert len(amqp_payload['pdus']) == 2

    pdu = amqp_payload['pdus'][0]
    # Spot check some pdu values
    assert pdu['source_addr'] == '447428666666'
    assert pdu['destination_addr'] == '447428555555'
    assert pdu['data_coding'] == 0
    assert pdu['more_messages_to_send'] == 1

    # Is a hex message (hexlified) as contains udh header
    # udh 5 0 3, 1 2 1 # ref 1, parts 2, no 1
    assert pdu['short_message_hex'].startswith('050003010201')

    pdu = amqp_payload['pdus'][1]
    # Spot check some pdu values
    assert pdu['source_addr'] == '447428666666'
    assert pdu['destination_addr'] == '447428555555'
    assert pdu['data_coding'] == 0
    assert pdu['more_messages_to_send'] == 0

    # Is a hex message (hexlified) as contains udh header
    # udh 5 0 3, 1 2 1 # ref 1, parts 2, no 2
    assert pdu['short_message_hex'].startswith('050003010202')
