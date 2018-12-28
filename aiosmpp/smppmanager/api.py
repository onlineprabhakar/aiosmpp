import logging
from typing import Optional, TYPE_CHECKING

from aiohttp import web

from aiosmpp.config.smpp import SMPPConfig

if TYPE_CHECKING:
    from aiosmpp.smppmanager.manager import SMPPManager


class WebHandler(object):
    def __init__(self, smpp_manager: 'SMPPManager', config: Optional[SMPPConfig] = None,
                 logger: Optional[logging.Logger] = None):
        self.config = config
        self.smpp_manager = smpp_manager

        self.logger = logger
        if not logger:
            self.logger = logging.getLogger()

    def app(self) -> web.Application:
        _app = web.Application()

        _app.add_routes((
            web.get('/api/v1/status', self.handler_api_v1_status),
            web.get('/api/v1/smpp/connectors', self.handler_api_v1_smpp_connectors),
        ))
        _app.on_startup.append(self.startup_tasks)
        _app.on_shutdown.append(self.teardown_tasks)

        return _app

    async def startup_tasks(self, _app):
        self.logger.info('Running SMPP Manager setup')
        await self.smpp_manager.setup()

    async def teardown_tasks(self, _app):
        self.logger.info('Running SMPP Manager teardown')
        await self.smpp_manager.teardown()

    async def handler_api_v1_smpp_connectors(self, request: web.Request) -> web.Response:
        self.logger.info('{0} requesting smpp connector info'.format(request.remote))

        result = {'connectors': {}}

        for conn_id, conn_tuple in self.smpp_manager.connectors.items():
            conn, _ = conn_tuple

            result['connectors'][conn_id] = {
                'state': conn.state.name,
                'config': conn.config
            }

        return web.json_response(result)

    async def handler_api_v1_status(self, request: web.Request) -> web.Response:
        self.logger.info('{0} requesting status'.format(request.remote))
        return web.Response(text='OK', status=200)
