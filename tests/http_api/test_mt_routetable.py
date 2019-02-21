from typing import Dict, Any

import pytest

from aiosmpp.config.smpp import SMPPConfig
from aiosmpp.httpapi.routetable import MTRouteTable


HTTPAPI_CONFIG = """[sqs]
use_fifo_for_sms_queues = true
# FYI if you do fifo on DLR, you cannot set message timeouts so
use_fifo_for_dlr = false
use_fifo_for_mo = false
region = eu-west-1

[smpp_bind:smpp_conn1]
host = 127.0.10.1
port = 2775
bind_type = TRX
ssl = no
systemid = test1
password = testpw

[smpp_bind:smpp_conn2]
host = 127.0.10.1
port = 2775
bind_type = TRX
ssl = no
systemid = test1
password = testpw

[smpp_bind:smpp_conn3]
host = 127.0.10.1
port = 2775
bind_type = TRX
ssl = no
systemid = test1
password = testpw

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

SMPP_OBJ1 = {
    'state': 'BOUND_TRX',
    'config': {
        'queue_name': 'conn_test1'
    }
}
SMPP_OBJ2 = {
    'state': 'UNBOUND',
    'config': {
        'queue_name': 'conn_test2'
    }
}
MT_EVENT1 = {
    'pdus': [],
    'to': '447400000001',
    'from': '447400000002',
    'timestamp': 1534782956.063949,
    'msg': 'hello world',
    'direction': 'MT',
    'tags': [],
    'dlr': {
        'url': 'http://example.org',
        'level': 3,
        'method': 'POST'
    }
}
MT_EVENT2 = {
    'pdus': [],
    'to': '447400000001',
    'from': '447400000002',
    'timestamp': 1534782956.063949,
    'msg': 'hello world',
    'direction': 'MT',
    'tags': [1337],
    'dlr': {
        'url': 'http://example.org',
        'level': 3,
        'method': 'POST'
    }
}
MT_EVENT3 = {
    'pdus': [],
    'to': '447400000001',
    'from': '447400000002',
    'timestamp': 1534782956.063949,
    'msg': 'hello world',
    'direction': 'MT',
    'tags': [666],
    'dlr': {
        'url': 'http://example.org',
        'level': 3,
        'method': 'POST'
    }
}


@pytest.fixture(scope='function')
def route_table() -> MTRouteTable:

    config = SMPPConfig.from_file(config=HTTPAPI_CONFIG)

    rt = MTRouteTable(config, route_attr='mt_routes')

    return rt


def test_route_order(route_table):

    route_numbers = [route.order for route in route_table.routes]
    route_numbers_sorted = sorted(route_numbers, reverse=True)

    assert route_numbers == route_numbers_sorted


def test_route_skip_to_defult(route_table):
    # MT_EVENT1 doesnt have tag 1337, or tag 666
    connector = route_table.evaluate(MT_EVENT1)

    assert connector is not None
    assert connector.name == 'smpp_conn1'


def test_route_1(route_table):
    # MT_EVENT1 doesnt have tag 1337, or tag 666
    connector = route_table.evaluate(MT_EVENT2)

    assert connector is not None
    assert connector.name == 'smpp_conn3'


def test_route_2(route_table):
    # MT_EVENT1 doesnt have tag 1337, or tag 666
    connector = route_table.evaluate(MT_EVENT3)

    assert connector is not None
    assert connector.name == 'smpp_conn2'


def test_route_skip_to_defult_missing(route_table):
    # Remove default route
    route_table.routes.pop(-1)

    assert route_table.routes[-1].order != 0

    connector = route_table.evaluate(MT_EVENT1)

    assert connector is None
