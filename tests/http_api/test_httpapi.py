from aiosmpp.config.httpapi import HTTPAPIConfig
from aiosmpp.httpapi.server import WebHandler


HTTPAPI_CONFIG = """[mq]
host = test
port = 1234
vhost = example
user = user
password = passwd
heartbeat_interval = 1

[somerandomsection]
test = 1

[smpp_client]
url = http://localhost:8081

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
        pass

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


def get_app():
    config = HTTPAPIConfig.from_file(config=HTTPAPI_CONFIG)
    mock = AMQPMock()
    handler = WebHandler(config=config, amqp_connect=mock)

    return mock, handler


async def test_next_long_message_ref_number_rollover():
    amqp_mock, handler = get_app()

    expected = 1
    while True:
        assert handler.next_long_msg_ref_num == expected

        expected += 1
        if expected == 256:
            expected = 1
            break
    assert handler.next_long_msg_ref_num == expected


async def test_status_api(aiohttp_client):
    amqp_mock, handler = get_app()
    client = await aiohttp_client(handler.app())

    resp = await client.get('/api/v1/status')
    assert resp.status == 200
