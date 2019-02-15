import argparse
import logging
import os
import sys

from aiosmpp.config.smpp import SMPPConfig
from aiosmpp.smppmanager.api import WebHandler
from aiosmpp.smppmanager.manager import SMPPManager
from aiosmpp.log import get_stdout_logger

from aiohttp import web


def app(argv: list = None) -> web.Application:
    parser = argparse.ArgumentParser(prog='HTTP API')

    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose mode')
    parser.add_argument('--config.file', help='Config file location')
    parser.add_argument('--config.dynamodb.table', help='DynamoDB config table')
    parser.add_argument('--config.dynamodb.region', help='DynamoDB region')
    parser.add_argument('--config.dynamodb.key', help='DynamoDB key identifying the config entry')

    args = parser.parse_args(argv[1:])

    log_level = logging.DEBUG if args.verbose else logging.INFO
    web_logger = get_stdout_logger('smppclient.api', log_level)
    manager_logger = get_stdout_logger('smppclient', log_level)

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

    print('Initialising SMPP Manager')
    smpp_manager = SMPPManager(config=config, logger=manager_logger)
    print('Initialising Web API')
    web_server = WebHandler(smpp_manager=smpp_manager, config=config, logger=web_logger)

    return web_server.app()


if __name__ == '__main__':
    print('Running server on 8081')
    web.run_app(app(sys.argv), port=8081, print=lambda x: None)
