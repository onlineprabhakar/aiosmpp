import asyncio
import base64
import datetime
import json
from collections import defaultdict
from unittest.mock import MagicMock

import pytest

from aiosmpp.smppmanager.manager import SMPPConnector
from aiosmpp import pdu
from aiosmpp import constants as const


class AIORedisStub(object):
    def __init__(self, data=None):
        self.call_count = 0
        self.calls = defaultdict(list)
        self._data = data or {}

    def clear_invocations(self):
        self.call_count = 0
        self.calls.clear()

    async def get(self, *args, **kwargs):
        self.call_count += 1
        self.calls['get'].append((args, kwargs))
        result = self._data.get(args[0])
        return result

    async def hset(self, *args, **kwargs):
        self.call_count += 1
        self.calls['hset'].append((args, kwargs))
        if args[0] not in self._data:
            self._data[args[0]] = {}
        self._data[args[0]][args[1]] = args[2]

    async def hvals(self, *args, **kwargs):
        self.call_count += 1
        self.calls['hvals'].append((args, kwargs))
        if args[0] not in self._data:
            result = None
        else:
            result = list(self._data[args[0]].values())

        return result

    async def expire(self, *args, **kwargs):
        self.call_count += 1
        self.calls['expire'].append((args, kwargs))


def AsyncMock(*args, **kwargs):
    m = MagicMock(*args, **kwargs)

    async def mock_coro(*args, **kwargs):
        return m(*args, **kwargs)

    mock_coro.mock = m
    return mock_coro


def get_mocked_connector(redis_mock: AIORedisStub = None):
    if not redis_mock:
        redis_mock = AIORedisStub()

    amqp_base = AsyncMock()
    amqp_mock = AsyncMock()
    amqp_base.basic_publish = amqp_mock

    config = {
        'queue_name': 'mock_smpp_connector',
        'connector_name': 'mock_connector',
        'mo_queue_name': 'mock_mo',
        'dlr_queue_name': 'mock_dlr'
    }
    new_connector = SMPPConnector(config=config, redis=redis_mock)
    new_connector._amqp_channel = amqp_base

    return new_connector, redis_mock, amqp_mock


# MO TODO for 100% coverage
# class2 encoding stuff
# singlepart mq exception
# multipart redis hset exception
# multipart redis hvals exception
# multipart mq exception


@pytest.mark.asyncio
async def test_process_mo_short():
    """
    Tests a standard short MO, non-multipayload
    """
    connector, redis, amqp = get_mocked_connector()

    msg = b'Hello'

    payload = pdu.deliver_sm(
        1,
        service_type='',
        source_addr_ton=const.AddrTON.INTERNATIONAL,
        source_addr_npi=const.AddrNPI.ISDN,
        source_addr='447111111111',
        dest_addr_ton=const.AddrTON.INTERNATIONAL,
        dest_addr_npi=const.AddrNPI.ISDN,
        dest_addr='447222222222',
        esm_class=int(const.ESMClassInbound.MESSAGE_TYPE_DEFAULT),
        protocol_id=0x00,
        priority_flag=int(const.PriorityFlag.LEVEL_0),
        schedule_delivery_time=None,  # Always Null
        validity_period=None,  # Always Null
        registered_delivery=const.RegisteredDeliveryReceipt.NO_SMSC_DELIVERY_RECEIPT_REQUESTED,
        replace_if_present_flag=0x00,  # Always Null
        data_coding=0x00,
        sm_default_msg_id=0x00,  # Always Null
        sm_length=len(msg),
        short_message=msg
    )

    mo_pkt_decoded = pdu.decode_header(payload)
    mo_pkt_decoded['payload'] = pdu.decode_deliver_sm(mo_pkt_decoded['payload'])

    # Test that a mo going through the generic deliver SM handler results in a co-routine that processes MO
    # Nasty hack for getting a task which is ensure_futured from a synchronous function
    tasks = asyncio.Task.all_tasks()
    connector.deliver_sm_trigger(mo_pkt_decoded)
    process_mo_task_list = list(asyncio.Task.all_tasks() - tasks)
    assert len(process_mo_task_list) == 1

    assert process_mo_task_list[0]._coro.__name__ == 'process_mo'
    await process_mo_task_list[0]
    # await connector.process_mo(mo_pkt_decoded)

    # Its a short MO, so no need to store parts in redis, call count should be 0
    assert redis.call_count == 0

    # Should be sent off to MQ
    assert amqp.mock.call_count == 1

    call_args = amqp.mock.call_args[1]
    assert call_args['routing_key'] == 'mock_mo'
    assert call_args['exchange_name'] == ''
    assert isinstance(call_args['payload'], str)

    payload = json.loads(call_args['payload'])

    assert 'id' in payload
    assert payload['id']

    assert payload['to'] == mo_pkt_decoded['payload']['dest_addr']
    assert payload['from'] == mo_pkt_decoded['payload']['source_addr']
    assert payload['coding'] == mo_pkt_decoded['payload']['data_coding']
    assert payload['origin-connector'] == 'mock_connector'
    assert base64.b64decode(payload['msg']) == mo_pkt_decoded['payload']['short_message']


@pytest.mark.asyncio
async def test_process_mo_sar_long_2parts():
    """
    Tests a sar multipart MO
    """
    connector, redis, amqp = get_mocked_connector()

    msg1 = b'Hello'
    msg2 = b' World'

    payload1 = pdu.deliver_sm(
        1,
        service_type='',
        source_addr_ton=const.AddrTON.INTERNATIONAL,
        source_addr_npi=const.AddrNPI.ISDN,
        source_addr='447111111111',
        dest_addr_ton=const.AddrTON.INTERNATIONAL,
        dest_addr_npi=const.AddrNPI.ISDN,
        dest_addr='447222222222',
        esm_class=int(const.ESMClassInbound.MESSAGE_TYPE_DEFAULT),
        protocol_id=0x00,
        priority_flag=int(const.PriorityFlag.LEVEL_0),
        schedule_delivery_time=None,  # Always Null
        validity_period=None,  # Always Null
        registered_delivery=const.RegisteredDeliveryReceipt.NO_SMSC_DELIVERY_RECEIPT_REQUESTED,
        replace_if_present_flag=0x00,  # Always Null
        data_coding=0x00,
        sm_default_msg_id=0x00,  # Always Null
        sm_length=len(msg1),
        short_message=msg1,
        tlvs=[
            pdu.create_tlv(pdu.TLV.sar_msg_ref_num, pdu.integer(1, 2), 2),  # ref 1, 2bytes
            pdu.create_tlv(pdu.TLV.sar_segment_seqnum, pdu.integer(1, 1), 1),  # sequence 1, 1byte
            pdu.create_tlv(pdu.TLV.sar_total_segments, pdu.integer(2, 1), 1),  # 2 parts, 1byte
        ]
    )
    payload2 = pdu.deliver_sm(
        2,
        service_type='',
        source_addr_ton=const.AddrTON.INTERNATIONAL,
        source_addr_npi=const.AddrNPI.ISDN,
        source_addr='447111111111',
        dest_addr_ton=const.AddrTON.INTERNATIONAL,
        dest_addr_npi=const.AddrNPI.ISDN,
        dest_addr='447222222222',
        esm_class=int(const.ESMClassInbound.MESSAGE_TYPE_DEFAULT),
        protocol_id=0x00,
        priority_flag=int(const.PriorityFlag.LEVEL_0),
        schedule_delivery_time=None,  # Always Null
        validity_period=None,  # Always Null
        registered_delivery=const.RegisteredDeliveryReceipt.NO_SMSC_DELIVERY_RECEIPT_REQUESTED,
        replace_if_present_flag=0x00,  # Always Null
        data_coding=0x00,
        sm_default_msg_id=0x00,  # Always Null
        sm_length=len(msg2),
        short_message=msg2,
        tlvs=[
            pdu.create_tlv(pdu.TLV.sar_msg_ref_num, pdu.integer(1, 2), 2),  # ref 1, 2bytes
            pdu.create_tlv(pdu.TLV.sar_segment_seqnum, pdu.integer(2, 1), 1),  # sequence 1, 1byte
            pdu.create_tlv(pdu.TLV.sar_total_segments, pdu.integer(2, 1), 1),  # 2 parts, 1byte
        ]
    )

    mo_pkt_decoded = pdu.decode_header(payload1)
    mo_pkt_decoded['payload'] = pdu.decode_deliver_sm(mo_pkt_decoded['payload'])

    await connector.process_mo(mo_pkt_decoded)

    # Its a multi-part MO so store it in redis, first a hset, then an expire
    assert redis.call_count == 2
    assert len(redis.calls['hset']) == 1
    assert len(redis.calls['expire']) == 1
    redis.clear_invocations()

    # Should not be sent to MQ
    assert amqp.mock.call_count == 0

    # Sent 2nd part
    mo_pkt_decoded = pdu.decode_header(payload2)
    mo_pkt_decoded['payload'] = pdu.decode_deliver_sm(mo_pkt_decoded['payload'])

    await connector.process_mo(mo_pkt_decoded)

    assert redis.call_count == 3
    assert len(redis.calls['hset']) == 1
    assert len(redis.calls['expire']) == 1
    assert len(redis.calls['hvals']) == 1

    # Should be sent off to MQ
    assert amqp.mock.call_count == 1

    call_args = amqp.mock.call_args[1]
    assert call_args['routing_key'] == 'mock_mo'
    assert call_args['exchange_name'] == ''
    assert isinstance(call_args['payload'], str)

    payload = json.loads(call_args['payload'])

    assert 'id' in payload
    assert payload['id']

    assert payload['to'] == mo_pkt_decoded['payload']['dest_addr']
    assert payload['from'] == mo_pkt_decoded['payload']['source_addr']
    assert payload['coding'] == mo_pkt_decoded['payload']['data_coding']
    assert payload['origin-connector'] == 'mock_connector'
    assert base64.b64decode(payload['msg']) == msg1 + msg2


@pytest.mark.asyncio
async def test_process_mo_udh_long_2parts():
    """
    Tests a sar multipart MO
    """
    connector, redis, amqp = get_mocked_connector()
    # length info  len  ref  total partno
    # \x05   \x00  \x03 \x01 \x02  \x01
    msg1 = b'\x05\x00\x03\x01\x02\x01Hello'
    msg2 = b'\x05\x00\x03\x01\x02\x02 World'

    payload1 = pdu.deliver_sm(
        1,
        service_type='',
        source_addr_ton=const.AddrTON.INTERNATIONAL,
        source_addr_npi=const.AddrNPI.ISDN,
        source_addr='447111111111',
        dest_addr_ton=const.AddrTON.INTERNATIONAL,
        dest_addr_npi=const.AddrNPI.ISDN,
        dest_addr='447222222222',
        esm_class=int(const.ESMClassInbound.MESSAGE_TYPE_DEFAULT | const.ESMClassInbound.GSM_FEATURES_UDHI),
        protocol_id=0x00,
        priority_flag=int(const.PriorityFlag.LEVEL_0),
        schedule_delivery_time=None,  # Always Null
        validity_period=None,  # Always Null
        registered_delivery=const.RegisteredDeliveryReceipt.NO_SMSC_DELIVERY_RECEIPT_REQUESTED,
        replace_if_present_flag=0x00,  # Always Null
        data_coding=0x00,
        sm_default_msg_id=0x00,  # Always Null
        sm_length=len(msg1),
        short_message=msg1
    )
    payload2 = pdu.deliver_sm(
        2,
        service_type='',
        source_addr_ton=const.AddrTON.INTERNATIONAL,
        source_addr_npi=const.AddrNPI.ISDN,
        source_addr='447111111111',
        dest_addr_ton=const.AddrTON.INTERNATIONAL,
        dest_addr_npi=const.AddrNPI.ISDN,
        dest_addr='447222222222',
        esm_class=int(const.ESMClassInbound.MESSAGE_TYPE_DEFAULT | const.ESMClassInbound.GSM_FEATURES_UDHI),
        protocol_id=0x00,
        priority_flag=int(const.PriorityFlag.LEVEL_0),
        schedule_delivery_time=None,  # Always Null
        validity_period=None,  # Always Null
        registered_delivery=const.RegisteredDeliveryReceipt.NO_SMSC_DELIVERY_RECEIPT_REQUESTED,
        replace_if_present_flag=0x00,  # Always Null
        data_coding=0x00,
        sm_default_msg_id=0x00,  # Always Null
        sm_length=len(msg2),
        short_message=msg2
    )

    mo_pkt_decoded = pdu.decode_header(payload1)
    mo_pkt_decoded['payload'] = pdu.decode_deliver_sm(mo_pkt_decoded['payload'])

    await connector.process_mo(mo_pkt_decoded)

    # Its a multi-part MO so store it in redis, first a hset, then an expire
    assert redis.call_count == 2
    assert len(redis.calls['hset']) == 1
    assert len(redis.calls['expire']) == 1
    redis.clear_invocations()

    # Should not be sent to MQ
    assert amqp.mock.call_count == 0

    # Sent 2nd part
    mo_pkt_decoded = pdu.decode_header(payload2)
    mo_pkt_decoded['payload'] = pdu.decode_deliver_sm(mo_pkt_decoded['payload'])

    await connector.process_mo(mo_pkt_decoded)

    assert redis.call_count == 3
    assert len(redis.calls['hset']) == 1
    assert len(redis.calls['expire']) == 1
    assert len(redis.calls['hvals']) == 1

    # Should be sent off to MQ
    assert amqp.mock.call_count == 1

    call_args = amqp.mock.call_args[1]
    assert call_args['routing_key'] == 'mock_mo'
    assert call_args['exchange_name'] == ''
    assert isinstance(call_args['payload'], str)

    payload = json.loads(call_args['payload'])

    assert 'id' in payload
    assert payload['id']

    assert payload['to'] == mo_pkt_decoded['payload']['dest_addr']
    assert payload['from'] == mo_pkt_decoded['payload']['source_addr']
    assert payload['coding'] == mo_pkt_decoded['payload']['data_coding']
    assert payload['origin-connector'] == 'mock_connector'
    assert base64.b64decode(payload['msg']) == msg1[6:] + msg2[6:]


@pytest.mark.asyncio
async def test_process_mo_udh_long_2parts_missing_one():
    """
    Tests a sar multipart MO
    """
    connector, redis, amqp = get_mocked_connector()
    # length info  len  ref  total partno
    # \x05   \x00  \x03 \x01 \x02  \x01
    msg2 = b'\x05\x00\x03\x01\x02\x02 World'

    payload2 = pdu.deliver_sm(
        2,
        service_type='',
        source_addr_ton=const.AddrTON.INTERNATIONAL,
        source_addr_npi=const.AddrNPI.ISDN,
        source_addr='447111111111',
        dest_addr_ton=const.AddrTON.INTERNATIONAL,
        dest_addr_npi=const.AddrNPI.ISDN,
        dest_addr='447222222222',
        esm_class=int(const.ESMClassInbound.MESSAGE_TYPE_DEFAULT | const.ESMClassInbound.GSM_FEATURES_UDHI),
        protocol_id=0x00,
        priority_flag=int(const.PriorityFlag.LEVEL_0),
        schedule_delivery_time=None,  # Always Null
        validity_period=None,  # Always Null
        registered_delivery=const.RegisteredDeliveryReceipt.NO_SMSC_DELIVERY_RECEIPT_REQUESTED,
        replace_if_present_flag=0x00,  # Always Null
        data_coding=0x00,
        sm_default_msg_id=0x00,  # Always Null
        sm_length=len(msg2),
        short_message=msg2
    )
    # Sent 2nd part
    mo_pkt_decoded = pdu.decode_header(payload2)
    mo_pkt_decoded['payload'] = pdu.decode_deliver_sm(mo_pkt_decoded['payload'])

    await connector.process_mo(mo_pkt_decoded)

    assert redis.call_count == 3
    assert len(redis.calls['hset']) == 1
    assert len(redis.calls['expire']) == 1
    assert len(redis.calls['hvals']) == 1

    # Should be sent off to MQ
    assert amqp.mock.call_count == 1

    call_args = amqp.mock.call_args[1]
    assert call_args['routing_key'] == 'mock_mo'
    assert call_args['exchange_name'] == ''
    assert isinstance(call_args['payload'], str)

    payload = json.loads(call_args['payload'])

    assert 'id' in payload
    assert payload['id']

    assert payload['to'] == mo_pkt_decoded['payload']['dest_addr']
    assert payload['from'] == mo_pkt_decoded['payload']['source_addr']
    assert payload['coding'] == mo_pkt_decoded['payload']['data_coding']
    assert payload['origin-connector'] == 'mock_connector'
    assert base64.b64decode(payload['msg']) == msg2[6:]


# DLR TODO for 100% coverage
# dlr_data not valid
# redis exception
# no redis data
# mq exception
# legit


@pytest.mark.asyncio
async def test_process_dlr_success():
    """
    Tests a standard short MO, non-multipayload
    """

    mt_id = 'mt_id1'
    dlr_method = 'POST'
    dlr_url = 'http://example.org'

    redis = AIORedisStub(data={'testid1': json.dumps({'id': mt_id, 'method': dlr_method, 'url': dlr_url})})
    connector, redis, amqp = get_mocked_connector(redis_mock=redis)

    msg_id = 'testid1'
    submit_time = datetime.datetime.now()
    state = const.MessageState.DELIVERED

    msg = 'id:{0} sub:001 dlvrd:001 submit date:{1} done date:{2} stat:{3} err:000 text:'.format(
        msg_id,
        submit_time.strftime('%y%M%d%H%M'),
        submit_time.strftime('%y%M%d%H%M'),
        state.short
    ).encode()

    payload = pdu.deliver_sm(
        1,
        service_type='',
        source_addr_ton=const.AddrTON.INTERNATIONAL,
        source_addr_npi=const.AddrNPI.ISDN,
        source_addr='447111111111',
        dest_addr_ton=const.AddrTON.INTERNATIONAL,
        dest_addr_npi=const.AddrNPI.ISDN,
        dest_addr='447222222222',
        esm_class=int(const.ESMClassInbound.MESSAGE_TYPE_CONTAINS_DELIVERY_ACK),
        protocol_id=0x00,
        priority_flag=int(const.PriorityFlag.LEVEL_0),
        schedule_delivery_time=None,
        validity_period=None,
        registered_delivery=const.RegisteredDeliveryReceipt.SMSC_DELIVERY_RECEIPT_REQUESTED,
        replace_if_present_flag=0x00,
        data_coding=0x00,
        sm_default_msg_id=0x00,
        sm_length=len(msg),
        short_message=msg
    )

    dlr_pkt_decoded = pdu.decode_header(payload)
    dlr_pkt_decoded['payload'] = pdu.decode_deliver_sm(dlr_pkt_decoded['payload'])

    # Test that a mo going through the generic deliver SM handler results in a co-routine that processes MO
    # Nasty hack for getting a task which is ensure_futured from a synchronous function
    tasks = asyncio.Task.all_tasks()
    connector.deliver_sm_trigger(dlr_pkt_decoded)
    process_dlr_task_list = list(asyncio.Task.all_tasks() - tasks)
    assert len(process_dlr_task_list) == 1

    assert process_dlr_task_list[0]._coro.__name__ == 'process_dlr'
    await process_dlr_task_list[0]
    # await connector.process_mo(mo_pkt_decoded)

    # Its a DLR, so it'll go to redis and attempt to get DLR data
    assert redis.call_count == 1
    assert len(redis.calls['get']) == 1
    redis_call_args, redis_call_kwargs = redis.calls['get'][0]
    assert redis_call_args[0] == 'testid1'

    # Should be sent off to MQ
    assert amqp.mock.call_count == 1

    call_args = amqp.mock.call_args[1]
    assert call_args['routing_key'] == 'mock_dlr'
    assert call_args['exchange_name'] == ''
    assert isinstance(call_args['payload'], str)

    payload = json.loads(call_args['payload'])

    assert payload['id'] == mt_id
    assert payload['id_smsc'] == msg_id
    assert payload['connector'] == 'mock_connector'
    assert payload['level'] == 3
    assert payload['method'] == dlr_method
    assert payload['url'] == dlr_url
    assert payload['message_status'] == state.short
    assert payload['subdate'] == submit_time.strftime('%y%M%d%H%M')
    assert payload['donedate'] == submit_time.strftime('%y%M%d%H%M')
    assert payload['sub'] == '001'
    assert payload['dlvrd'] == '001'
    assert payload['err'] == '000'
    assert payload['text'] == ''
