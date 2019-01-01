import asyncio
import aiohttp

import pytest

# pytest.mark.asyncio is required so that the test is ran in a
# different event loop than the fixture, otherwise the server doesnt serve :/
#
#     a1 = id(asyncio.get_event_loop())
#     a2 = id(server._loop)
#     print(server.port)


# @pytest.mark.asyncio
# async def test_status(http_api_server, mt_server_1, mt_server_2, mt_server_3):
#     handler, server, base_url = http_api_server
#
#     async with aiohttp.ClientSession() as sess:
#         async with sess.get(base_url + 'api/v1/status') as resp:
#             assert resp.status == 200
#             assert await resp.text() == 'OK'


@pytest.mark.asyncio
async def test_mt(http_api_server, mt_server_1, mt_server_2, mt_server_3):
    handler, server, base_url = http_api_server

    payload = {
        'content': '£ test',
        'to': '447428555555',
        'from': '447428666666',
        'username': 'test',
        'password': 'test',
        'coding': '0'
    }

    print()

    async with aiohttp.ClientSession() as sess:
        async with sess.get(base_url + 'send', params=payload) as resp:
            assert resp.status == 200
            text = await resp.text()

    print()