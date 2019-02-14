from aiosmpp.config.smpp import SMPPConfig
from aiosmpp.sqs import MockSQSManager
from aiosmpp.httpapi.server import WebHandler


def get_app(conf_data: bytes):
    config = SMPPConfig.from_file(config=conf_data.decode())
    handler = WebHandler(config=config, sqs_manager=MockSQSManager)

    return handler


async def test_next_long_message_ref_number_rollover(get_resource):
    handler = get_app(get_resource('smpp.conf'))
    sqs = handler._sqs

    expected = 1
    while True:
        assert handler.next_long_msg_ref_num == expected

        expected += 1
        if expected == 256:
            expected = 1
            break
    assert handler.next_long_msg_ref_num == expected


async def test_status_api(aiohttp_client, get_resource):
    handler = get_app(get_resource('smpp.conf'))
    sqs = handler._sqs

    client = await aiohttp_client(handler.app())

    resp = await client.get('/api/v1/status')
    assert resp.status == 200
