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

        return _app

    async def startup_tasks(self, _app):
        print('Running SMPP Manager setup')
        await self.smpp_manager.setup()

    async def handler_api_v1_smpp_connections(self, request: web.Request) -> web.Response:
        result = {'connections': {}}

        for conn_id, conn in self.smpp_manager.connectors.items():
            result['connections'][conn_id] = {
                'state': str(conn.state),
                'config': conn.config
            }

        return web.json_response(result)

    async def handler_api_v1_status(self, request: web.Request) -> web.Response:
        return web.Response(text='OK', status=200)


def app(argv: list=None) -> web.Application:
    parser = argparse.ArgumentParser(prog='HTTP API')

    # --config.file
    parser.add_argument('--config.file', help='Config file location')
    parser.add_argument('--config.dynamodb.table', help='DynamoDB config table')
    parser.add_argument('--config.dynamodb.region', help='DynamoDB region')
    parser.add_argument('--config.dynamodb.key', help='DynamoDB key identifying the config entry')

    args = parser.parse_args(argv[1:])

    config = None
    if getattr(args, 'config.file') and getattr(args, 'config.dynamodb.table'):
        print('Cannot specify both dynamodb and file')
        sys.exit(1)
    elif getattr(args, 'config.dynamodb.table'):
        raise NotImplementedError()
    elif getattr(args, 'config.file'):
        filepath = os.path.expanduser(getattr(args, 'config.file'))
        if not os.path.exists(filepath):
            print('Path "{0}" does not exist, exiting'.format(filepath))
            sys.exit(1)

        config = SMPPConfig.from_file(filepath)

    web_server = WebHandler(config=config)
    return web_server.app()


if __name__ == '__main__':
    web.run_app(app(sys.argv))
