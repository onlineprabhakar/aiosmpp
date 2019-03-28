import logging
import time
import uuid
from typing import Optional, TYPE_CHECKING

from aiohttp import web
import aioprometheus

from aiosmpp.config.smpp import SMPPConfig
from aiosmpp.log import get_http_access_logger
from aiosmpp.sentry_shim import sentry_middleware

if TYPE_CHECKING:
    from aiosmpp.smppmanager.manager import SMPPManager


web_logger = get_http_access_logger(name='smppclient.http', sentry_client=sentry_middleware.client)


class WebHandler(object):
    def __init__(self, smpp_manager: 'SMPPManager', config: Optional[SMPPConfig] = None,
                 logger: Optional[logging.Logger] = None):
        self.config = config
        self.smpp_manager = smpp_manager

        self.logger = logger
        if not logger:
            self.logger = logging.getLogger()

        self._http_request_metric = aioprometheus.Histogram('http_request_duration_seconds', 'HTTP Request duration')
        self._prometheus_registery = aioprometheus.Registry()

        self._prometheus_registery.register(self._http_request_metric)

    def app(self) -> web.Application:
        _app = web.Application(middlewares=[
            logging_middleware,
            sentry_middleware
        ])

        _app.add_routes((
            web.get('/api/v1/status', self.handler_api_v1_status),
            web.get('/api/v1/smpp/connectors', self.handler_api_v1_smpp_connectors),
        ))

        _app['registry'] = self._prometheus_registery
        _app['metrics_http_access'] = self._http_request_metric
        _app.on_startup.append(self.startup_tasks)
        _app.on_shutdown.append(self.teardown_tasks)

        return _app

    async def startup_tasks(self, _app: web.Application):
        self.logger.info('Running SMPP Manager setup')
        await self.smpp_manager.setup()

    async def teardown_tasks(self, _app: web.Application):
        self.logger.info('Running SMPP Manager teardown')
        await self.smpp_manager.teardown()

    async def handler_api_v1_smpp_connectors(self, request: web.Request) -> web.Response:
        self.logger.info('{0} requesting smpp connector info'.format(request.remote))

        result = {'connectors': {}}

        for conn_id, conn_tuple in self.smpp_manager.connectors.items():
            conn, _ = conn_tuple

            result['connectors'][conn_id] = conn.state.name

        return web.json_response(result)

    async def handler_api_v1_status(self, request: web.Request) -> web.Response:
        self.logger.info('{0} requesting status'.format(request.remote))
        return web.Response(text='OK', status=200)


@web.middleware
async def logging_middleware(request: web.Request, handler) -> web.Response:
    start_time = time.perf_counter()
    request['req_id'] = str(uuid.uuid4())

    response: web.Response = await handler(request)

    total_time = (time.perf_counter() - start_time)
    if 'metrics_http_access' in request.app:
        # Record metrics
        request.app['metrics_http_access'].add({'path': request.path, 'status': response.status}, total_time)
    web_logger.info(None, extra={'request': request, 'response': response, 'time': total_time})

    return response
