import asyncio
import aiohttp
import time
import pytest

# pytest.mark.asyncio is required so that the test is ran in a
# different event loop than the fixture, otherwise the server doesnt serve :/
#
#     a1 = id(asyncio.get_event_loop())
#     a2 = id(server._loop)
#     print(server.port)


@pytest.mark.asyncio
async def test_status(http_api_server):
    handler, server, base_url = http_api_server

    async with aiohttp.ClientSession() as sess:
        async with sess.get(base_url + 'api/v1/status') as resp:
            assert resp.status == 200
            assert await resp.text() == 'OK'


@pytest.mark.asyncio
async def test_mt(http_api_server, mt_server_1, mt_server_2, mt_server_3):
    handler, server, base_url = http_api_server

    mt_server_1_mt = mt_server_1[2]
    mt_server_2_mt = mt_server_2[2]
    mt_server_3_mt = mt_server_3[2]

    payload = {
        'content': '£ test',
        'to': '447428555555',
        'from': '447428666666',
        'username': 'test',
        'password': 'test',
        'coding': '0'
    }

    async with aiohttp.ClientSession() as sess:
        async with sess.get(base_url + 'send', params=payload) as resp:
            status = resp.status
            text = await resp.text()

    assert status == 200
    assert "Success" in text

    time.sleep(5)

    # We have no tag, so it wont hit 2,3
    assert mt_server_1_mt
    assert mt_server_1_mt[0]['short_message'] == b'\x01 test'  # \x01 is £ in GSM7

    payload = {
        'content': '£ test',
        'to': '447428555555',
        'from': '447428666666',
        'username': 'test',
        'password': 'test',
        'coding': '0',
        'tags': '1337'
    }

    async with aiohttp.ClientSession() as sess:
        async with sess.get(base_url + 'send', params=payload) as resp:
            status = resp.status
            text = await resp.text()

    assert status == 200
    assert "Success" in text

    time.sleep(5)

    # Has 1337 tag, so will hit 3
    assert mt_server_3_mt
    assert mt_server_3_mt[0]['short_message'] == b'\x01 test'  # \x01 is £ in GSM7

    payload = {
        'content': '£ test',
        'to': '447428555555',
        'from': '447428666666',
        'username': 'test',
        'password': 'test',
        'coding': '0',
        'tags': '666'
    }

    async with aiohttp.ClientSession() as sess:
        async with sess.get(base_url + 'send', params=payload) as resp:
            status = resp.status
            text = await resp.text()

    assert status == 200
    assert "Success" in text

    time.sleep(5)

    # Has 1337 tag, so will hit 3
    assert mt_server_2_mt
    assert mt_server_2_mt[0]['short_message'] == b'\x01 test'  # \x01 is £ in GSM7
