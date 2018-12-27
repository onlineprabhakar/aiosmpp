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

MO_EVENT1 = {
    'pdus': [],
    'to': '447400000001',
    'from': '447400000002',
    'timestamp': 1534782956.063949,
    'msg': 'hello world',
    'direction': 'MT',
    'tags': [1, 5, 70],
    'origin-connector': 'test1'
}


def test_transparent_filter():
    filter_obj = routetable.TransparentFilter()

    assert filter_obj.evaluate(MT_EVENT1)


def test_connection_filter():
    filter_obj = routetable.ConnectorFilter(connector='test1')
    assert filter_obj.evaluate(MO_EVENT1)

    filter_obj = routetable.ConnectorFilter(connector='test11')
    assert not filter_obj.evaluate(MO_EVENT1)


def test_source_addr_filter():
    filter_obj = routetable.SourceAddrFilter(filter_regex='.*400000001')
    assert filter_obj.evaluate(MT_EVENT1)

    filter_obj = routetable.SourceAddrFilter(filter_regex='.*400000002')
    assert not filter_obj.evaluate(MT_EVENT1)


def test_dest_addr_filter():
    filter_obj = routetable.DestinationAddrFilter(filter_regex='.*400000002')
    assert filter_obj.evaluate(MT_EVENT1)

    filter_obj = routetable.DestinationAddrFilter(filter_regex='.*400000001')
    assert not filter_obj.evaluate(MT_EVENT1)


def test_msg_filter():
    filter_obj = routetable.ShortMessageFilter(filter_regex='.*world')
    assert filter_obj.evaluate(MT_EVENT1)

    filter_obj = routetable.ShortMessageFilter(filter_regex='.*test')
    assert not filter_obj.evaluate(MT_EVENT1)


def test_tag_filter():
    filter_obj = routetable.TagFilter(tag=1)
    assert filter_obj.evaluate(MT_EVENT1)

    filter_obj = routetable.TagFilter(tag=5)
    assert filter_obj.evaluate(MT_EVENT1)

    filter_obj = routetable.TagFilter(tag=20)
    assert not filter_obj.evaluate(MT_EVENT1)


# TODO test get_filter()

