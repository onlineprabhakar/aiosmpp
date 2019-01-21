import asyncio
import argparse
import logging
import sys
import os
import json

import aioamqp
from aiosmpp.config.httpapi import HTTPAPIConfig
from aiosmpp.log import get_stdout_logger

DLR_QUEUE = 'dlr'


async def amqp_callback(channel, body, envelope, properties):

    data = json.loads(body)

    print('Got {0}'.format(data['id']))
    if envelope.is_redeliver:
        print('Acking')
        await channel.basic_client_ack(envelope.delivery_tag)
    else:
        print('Nacking')
        await channel.basic_client_nack(envelope.delivery_tag)



async def main():
    parser = argparse.ArgumentParser(prog='HTTP API')

    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose mode')
    parser.add_argument('--config.file', help='Config file location')
    parser.add_argument('--config.dynamodb.table', help='DynamoDB config table')
    parser.add_argument('--config.dynamodb.region', help='DynamoDB region')
    parser.add_argument('--config.dynamodb.key', help='DynamoDB key identifying the config entry')

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logger = get_stdout_logger('dlrposter', log_level)
    conf_logger = get_stdout_logger('dlrposter.config', log_level)

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

        config = HTTPAPIConfig.from_file(filepath, logger=conf_logger)

    transport, protocol = await aioamqp.connect(
        host=config.mq['host'],
        port=config.mq['port'],
        login=config.mq['user'],
        password=config.mq['password'],
        virtualhost=config.mq['vhost'],
        ssl=config.mq['ssl'],
        heartbeat=config.mq['heartbeat_interval']
    )
    channel = await protocol.channel()

    # Declare queue
    await channel.queue_declare(queue_name=DLR_QUEUE, durable=True)

    await channel.basic_consume(amqp_callback, queue_name=DLR_QUEUE)

    try:
        while True:
            await asyncio.sleep(1)

    except asyncio.CancelledError:
        pass
    finally:
        await protocol.close()
        transport.close()



asyncio.get_event_loop().run_until_complete(main())