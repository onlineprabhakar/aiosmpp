import argparse
import os
import sys
from typing import Optional, TYPE_CHECKING

from aiohttp import web

from aiosmpp.config.smpp import SMPPConfig

if TYPE_CHECKING:
    from aiosmpp.smppmanager.manager import SMPPManager


class WebHandler(object):
    def __init__(self, smpp_manager: 'SMPPManager', config: Optional[SMPPConfig]=None):
        self.config = config
        self.smpp_manager = smpp_manager

    def app(self) -> web.Application:
        _app = web.Application()

        _app.add_routes((
            web.get('/api/v1/status', self.handler_api_v1_status),
            web.get('/api/v1/smpp/connections', self.handler_api_v1_smpp_connections),
        ))
        _app.on_startup.append(self.startup_tasks)

        return _app

    async def startup_tasks(self, _app):
        print('Running SMPP Manager setup')
        await self.smpp_manager.setup()

    async def handler_api_v1_smpp_connections(self, request: web.Request) -> web.Response:
        result = {'connections': {}}

        for conn_id, conn_tuple in self.smpp_manager.connectors.items():
            conn, _ = conn_tuple

            result['connections'][conn_id] = {
                'state': str(conn.state),
                'config': conn.config
            }

        return web.json_response(result)

    async def handler_api_v1_status(self, request: web.Request) -> web.Response:
        return web.Response(text='OK', status=200)
