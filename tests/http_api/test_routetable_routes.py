import pytest

from aiosmpp.httpapi import routetable


MT_EVENT1 = {
    'pdus': [],
    'to': '447400000001',
    'from': '447400000002',
    'timestamp': 1534782956.063949,
    'msg': 'hello world',
    'direction': 'MT',
    'tags': [1, 5, 70],
    'dlr': {
        'url': 'http://example.org',
        'level': 3,
        'method': 'POST'
    }
}

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


def test_smpp_connector_obj():
    conn = routetable.SMPPConnector('test1', SMPP_OBJ1)

    assert conn.queue_name == SMPP_OBJ1['config']['queue_name']

    data_dict = conn.to_dict()
    assert data_dict['name'] == conn.name
    assert 'data' in data_dict

    new_conn = routetable.SMPPConnector.from_dict(data_dict)
    assert new_conn.name == conn.name
    assert new_conn.queue_name == conn.queue_name


def test_route_obj():
    conn_dict = {'connectors': {}}

    # Abuses conn_dict reference
    route = routetable.Route(0, 'test1', [], conn_dict)
    conn_dict['connectors']['test1'] = SMPP_OBJ1

    assert isinstance(route.connector, routetable.SMPPConnector)

    del conn_dict['connectors']['test1']
    assert route.connector is None  # Test it works when no routes are there

    conn_dict['connectors']['test1'] = SMPP_OBJ2

    assert route.connector is None  # Test it works when the smpp connection is unbound

    with pytest.raises(NotImplementedError):
        route.evaluate(MT_EVENT1)


def test_static_route_no_connector():
    conn_dict = {'connectors': {}}
    route = routetable.StaticRoute(0, 'test1', [], conn_dict)

    assert not route.evaluate(MT_EVENT1)


def test_static_route_filters():
    conn_dict = {'connectors': {}}
    msg_filter1 = routetable.ShortMessageFilter(filter_regex='.*world')
    msg_filter2 = routetable.ShortMessageFilter(filter_regex='.*test')

    route = routetable.StaticRoute(0, 'test1', [msg_filter1], conn_dict)
    conn_dict['connectors']['test1'] = SMPP_OBJ1

    assert route.evaluate(MT_EVENT1)

    route = routetable.StaticRoute(0, 'test1', [msg_filter2], conn_dict)

    assert not route.evaluate(MT_EVENT1)


def test_static_route_repr():
    route = routetable.StaticRoute(0, 'test1', [], None)
    result = repr(route)

    assert 'StaticRoute' in result





