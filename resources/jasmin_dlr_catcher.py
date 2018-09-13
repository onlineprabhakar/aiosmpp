import argparse
import binascii
import datetime
import math
import os
import struct
import sys
from typing import Dict, Any, Optional, TYPE_CHECKING

from aiohttp import web


class WebHandler(object):
    def app(self) -> web.Application:
        _app = web.Application()

        _app.add_routes((
            web.post('/dlr', self.handle_dlr)
        ))

        return _app

    # Legacy send
    async def handle_dlr(self, request: web.Request) -> web.Response:
        # Parse / Validate form data
        try:
            form_data = await request.post()
            print(form_data)
        except Exception as err:
            pass

        return web.Response(text='ACK/Jasmin', status=200)


def app(argv: list=None) -> web.Application:
    return WebHandler().app()


if __name__ == '__main__':
    web.run_app(app(sys.argv), port=8080)
