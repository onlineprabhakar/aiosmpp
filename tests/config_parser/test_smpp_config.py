import pytest

from aiosmpp.config import smpp

CONFIG = """[sqs]
# prefix =
# endpoint =
use_fifo_for_sms_queues = true
# FYI if you do fifo on DLR, you cannot set message timeouts so
use_fifo_for_dlr = false
use_fifo_for_mo = false
region = eu-west-1

[smpp_client]
url = http://localhost:8081

[somerandomsection]
test = 1

[mt_route:20]
type = static
connector = smpp_conn3
filters = tag_filter

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


def test_config_error():
    with pytest.raises(ValueError):
        smpp.SMPPConfig.from_file()


def test_config():
    config = smpp.SMPPConfig.from_file(config=CONFIG)

    for name in ('tag_filter1', 'tag_filter2', 'uk_addr'):
        assert name in config.filters

    assert config.filters['tag_filter1']['type'] == 'tag'

    for name in ('0', '10', '20'):
        assert name in config.mt_routes

    assert config.mt_routes['0']['type'] == 'default'
    assert config.mt_routes['0']['connector'] == 'smpp_conn1'

    assert config.mq['region'] == 'eu-west-1'


def test_config_reload():
    config = smpp.SMPPConfig.from_file(config=CONFIG)

    config.reload()

    for name in ('tag_filter1', 'tag_filter2', 'uk_addr'):
        assert name in config.filters

    for name in ('0', '10', '20'):
        assert name in config.mt_routes

    assert config.mq['region'] == 'eu-west-1'
