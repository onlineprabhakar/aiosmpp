from aiosmpp import filters


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
    filter_obj = filters.TransparentFilter()

    assert filter_obj.evaluate(MT_EVENT1)


def test_connection_filter():
    filter_obj = filters.ConnectorFilter(connector='test1')
    assert filter_obj.evaluate(MO_EVENT1)

    filter_obj = filters.ConnectorFilter(connector='test11')
    assert not filter_obj.evaluate(MO_EVENT1)


def test_source_addr_filter():
    filter_obj = filters.SourceAddrFilter(filter_regex='.*400000001')
    assert filter_obj.evaluate(MT_EVENT1)

    filter_obj = filters.SourceAddrFilter(filter_regex='.*400000002')
    assert not filter_obj.evaluate(MT_EVENT1)


def test_dest_addr_filter():
    filter_obj = filters.DestinationAddrFilter(filter_regex='.*400000002')
    assert filter_obj.evaluate(MT_EVENT1)

    filter_obj = filters.DestinationAddrFilter(filter_regex='.*400000001')
    assert not filter_obj.evaluate(MT_EVENT1)


def test_msg_filter():
    filter_obj = filters.ShortMessageFilter(filter_regex='.*world')
    assert filter_obj.evaluate(MT_EVENT1)

    filter_obj = filters.ShortMessageFilter(filter_regex='.*test')
    assert not filter_obj.evaluate(MT_EVENT1)


def test_tag_filter():
    filter_obj = filters.TagFilter(tag=1)
    assert filter_obj.evaluate(MT_EVENT1)

    filter_obj = filters.TagFilter(tag=5)
    assert filter_obj.evaluate(MT_EVENT1)

    filter_obj = filters.TagFilter(tag=20)
    assert not filter_obj.evaluate(MT_EVENT1)


def test_get_filter_transparent():
    filter_obj = filters.get_filter({'type': 'transparent'})
    assert isinstance(filter_obj, filters.TransparentFilter)

    filter_obj = filters.get_filter({'type': 'unknown'})
    assert isinstance(filter_obj, filters.TransparentFilter)

    filter_obj = filters.get_filter({})
    assert isinstance(filter_obj, filters.TransparentFilter)


def test_get_filter_tag():
    filter_obj = filters.get_filter({'type': 'tag', 'tag': '1'})
    assert isinstance(filter_obj, filters.TagFilter)


def test_get_filter_destination_addr():
    filter_obj = filters.get_filter({'type': 'destaddr', 'regex': 'test'})
    assert isinstance(filter_obj, filters.DestinationAddrFilter)
