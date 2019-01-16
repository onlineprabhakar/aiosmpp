from typing import Dict, Any

import pytest

from aiosmpp.config.httpapi import HTTPAPIConfig
from aiosmpp.httpapi.routetable import RouteTable


HTTPAPI_CONFIG = """[mq]
host = test
port = 1234
vhost = example
user = user
password = passwd
heartbeat_interval = 1

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
def connector_dict() -> Dict[str, Any]:
    connector_dict = {'connectors': {}}

    return connector_dict


@pytest.fixture(scope='function')
def route_table(connector_dict) -> RouteTable:

    config = HTTPAPIConfig.from_file(config=HTTPAPI_CONFIG)

    rt = RouteTable(config, route_attr='mt_routes', connector_dict=connector_dict)

    return rt


def test_route_order(route_table):

    route_numbers = [route.order for route in route_table.routes]
    route_numbers_sorted = sorted(route_numbers, reverse=True)

    assert route_numbers == route_numbers_sorted


def test_route_skip_to_defult(connector_dict, route_table):
    connector_dict['connectors']['smpp_conn3'] = SMPP_OBJ1
    connector_dict['connectors']['smpp_conn2'] = SMPP_OBJ1
    connector_dict['connectors']['smpp_conn1'] = SMPP_OBJ1

    # MT_EVENT1 doesnt have tag 1337, or tag 666
    connector = route_table.evaluate(MT_EVENT1)

    assert connector is not None
    assert connector.name == 'smpp_conn1'


def test_route_skip_to_defult_unbound(connector_dict, route_table):
    connector_dict['connectors']['smpp_conn3'] = SMPP_OBJ1
    connector_dict['connectors']['smpp_conn2'] = SMPP_OBJ1
    connector_dict['connectors']['smpp_conn1'] = SMPP_OBJ2

    # MT_EVENT1 doesnt have tag 1337, or tag 666
    connector = route_table.evaluate(MT_EVENT1)

    assert connector is None


def test_route_1(connector_dict, route_table):
    connector_dict['connectors']['smpp_conn3'] = SMPP_OBJ1
    connector_dict['connectors']['smpp_conn2'] = SMPP_OBJ1
    connector_dict['connectors']['smpp_conn1'] = SMPP_OBJ1

    # MT_EVENT1 doesnt have tag 1337, or tag 666
    connector = route_table.evaluate(MT_EVENT2)

    assert connector is not None
    assert connector.name == 'smpp_conn3'


def test_route_2(connector_dict, route_table):
    connector_dict['connectors']['smpp_conn3'] = SMPP_OBJ1
    connector_dict['connectors']['smpp_conn2'] = SMPP_OBJ1
    connector_dict['connectors']['smpp_conn1'] = SMPP_OBJ1

    # MT_EVENT1 doesnt have tag 1337, or tag 666
    connector = route_table.evaluate(MT_EVENT3)

    assert connector is not None
    assert connector.name == 'smpp_conn2'


def test_route_skip_to_defult_missing(connector_dict, route_table):
    connector_dict['connectors']['smpp_conn3'] = SMPP_OBJ1
    connector_dict['connectors']['smpp_conn2'] = SMPP_OBJ1
    connector_dict['connectors']['smpp_conn1'] = SMPP_OBJ2

    # Remove default route
    route_table.routes.pop(-1)

    assert route_table.routes[-1].order != 0

    connector = route_table.evaluate(MT_EVENT1)

    assert connector is None
