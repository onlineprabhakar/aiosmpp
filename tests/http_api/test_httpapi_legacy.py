import binascii
import json

from aiosmpp.config.smpp import SMPPConfig
from aiosmpp.httpapi.server import WebHandler
from aiosmpp.sqs import MockSQSManager


def get_app(conf_data: bytes):
    config = SMPPConfig.from_file(config=conf_data.decode())
    handler = WebHandler(config=config, sqs_manager=MockSQSManager)

    return handler


async def test_legacy_missing_param(aiohttp_client, get_resource):
    handler = get_app(get_resource('smpp.conf'))
    sqs = handler._sqs

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


async def test_legacy_no_route(aiohttp_client, get_resource):
    handler = get_app(get_resource('smpp.conf'))
    sqs = handler._sqs

    client = await aiohttp_client(handler.app())

    # Remove all routes
    handler.route_table.routes.clear()

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


async def test_legacy_send_gsm7(aiohttp_client, get_resource):
    handler = get_app(get_resource('smpp.conf'))
    sqs = handler._sqs

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

    assert sqs._queue_map
    queue = list(sqs._queue_map.values())[0]
    assert queue
    queue_msg = queue[0]

    # Check amqp data
    sqs_payload = json.loads(queue_msg['Body'])

    assert 'Success "{0}"'.format(sqs_payload['req_id']) in text

    assert sqs_payload['connector'] == 'smpp_conn1'
    assert len(sqs_payload['pdus']) == 1

    pdu = sqs_payload['pdus'][0]
    # Spot check some pdu values
    assert pdu['source_addr'] == '447428666666'
    assert pdu['destination_addr'] == '447428555555'
    assert pdu['data_coding'] == 0
    assert pdu['short_message'] == '\x01 test'
    assert pdu['sm_default_msg_id'] == 0


async def test_legacy_send_latin1(aiohttp_client, get_resource):
    handler = get_app(get_resource('smpp.conf'))
    sqs = handler._sqs

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

    assert sqs._queue_map
    queue = list(sqs._queue_map.values())[0]
    assert queue
    queue_msg = queue[0]

    # Check amqp data
    sqs_payload = json.loads(queue_msg['Body'])

    assert 'Success "{0}"'.format(sqs_payload['req_id']) in text

    assert sqs_payload['connector'] == 'smpp_conn1'
    assert len(sqs_payload['pdus']) == 1

    pdu = sqs_payload['pdus'][0]
    # Spot check some pdu values
    assert pdu['source_addr'] == '447428666666'
    assert pdu['destination_addr'] == '447428555555'
    assert pdu['data_coding'] == 3
    assert pdu['short_message'] == '£ test'
    assert pdu['sm_default_msg_id'] == 0


async def test_legacy_send_ucs2(aiohttp_client, get_resource):
    handler = get_app(get_resource('smpp.conf'))
    sqs = handler._sqs

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

    assert sqs._queue_map
    queue = list(sqs._queue_map.values())[0]
    assert queue
    queue_msg = queue[0]

    # Check amqp data
    sqs_payload = json.loads(queue_msg['Body'])

    assert 'Success "{0}"'.format(sqs_payload['req_id']) in text

    assert sqs_payload['connector'] == 'smpp_conn1'
    assert len(sqs_payload['pdus']) == 1

    pdu = sqs_payload['pdus'][0]
    # Spot check some pdu values
    assert pdu['source_addr'] == '447428666666'
    assert pdu['destination_addr'] == '447428555555'
    assert pdu['data_coding'] == 8
    assert pdu['short_message_hex'] == content
    assert pdu['sm_default_msg_id'] == 0


async def test_legacy_send_gsm7_long(aiohttp_client, get_resource):
    handler = get_app(get_resource('smpp.conf'))
    sqs = handler._sqs

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

    assert sqs._queue_map
    queue = list(sqs._queue_map.values())[0]
    assert queue
    queue_msg = queue[0]

    # Check amqp data
    sqs_payload = json.loads(queue_msg['Body'])

    assert 'Success "{0}"'.format(sqs_payload['req_id']) in text

    assert sqs_payload['connector'] == 'smpp_conn1'
    assert len(sqs_payload['pdus']) == 2

    pdu = sqs_payload['pdus'][0]
    # Spot check some pdu values
    assert pdu['source_addr'] == '447428666666'
    assert pdu['destination_addr'] == '447428555555'
    assert pdu['data_coding'] == 0
    assert pdu['more_messages_to_send'] == 1

    # Is a hex message (hexlified) as contains udh header
    # udh 5 0 3, 1 2 1 # ref 1, parts 2, no 1
    assert pdu['short_message_hex'].startswith('050003010201')

    pdu = sqs_payload['pdus'][1]
    # Spot check some pdu values
    assert pdu['source_addr'] == '447428666666'
    assert pdu['destination_addr'] == '447428555555'
    assert pdu['data_coding'] == 0
    assert pdu['more_messages_to_send'] == 0

    # Is a hex message (hexlified) as contains udh header
    # udh 5 0 3, 1 2 1 # ref 1, parts 2, no 2
    assert pdu['short_message_hex'].startswith('050003010202')
