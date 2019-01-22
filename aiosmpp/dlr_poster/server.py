import asyncio
import argparse
import logging
import sys
import os
import json

import aiohttp
import aioamqp
from aiosmpp.config.httpapi import HTTPAPIConfig
from aiosmpp.log import get_stdout_logger
from aiosmpp.constants import DLR_QUEUE


# TODO make configurable
RETRY_COUNT = 5


class DLRPoster(object):
    def __init__(self, config: HTTPAPIConfig, logger: logging.Logger):
        self.logger = logger
        self.config = config

        self.http_session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(verify_ssl=False))

        self.amqp_transport = None
        self.amqp_protocol = None
        self.amqp_channel = None

    async def close(self):
        self.logger.info('Stopping DLR Poster')
        await self.http_session.close()
        await self.amqp_protocol.close()
        self.amqp_transport.close()
        self.logger.info('Tore down DLR Poster connections')

    async def setup(self):
        self.logger.info('Starting DLR Poster setup')
        self.logger.debug('Connecting to MQ {0}:{1}'.format(self.config.mq['host'], self.config.mq['port']))
        self.amqp_transport, self.amqp_protocol = await aioamqp.connect(
            host=self.config.mq['host'],
            port=self.config.mq['port'],
            login=self.config.mq['user'],
            password=self.config.mq['password'],
            virtualhost=self.config.mq['vhost'],
            ssl=self.config.mq['ssl'],
            heartbeat=self.config.mq['heartbeat_interval']
        )
        self.amqp_channel = await self.amqp_protocol.channel()
        self.logger.info('Connected to MQ {0}:{1}'.format(self.config.mq['host'], self.config.mq['port']))

        # Declare queue
        await self.amqp_channel.queue_declare(queue_name=DLR_QUEUE, durable=True)
        self.logger.info('Declared queue {0}'.format(DLR_QUEUE))
        self.logger.info('Finished DLR Poster setup')

    async def run(self):
        # TODO make the qos configurable
        await self.amqp_channel.basic_qos(prefetch_count=8, prefetch_size=0, connection_global=False)
        await self.amqp_channel.basic_consume(self.amqp_callback, queue_name=DLR_QUEUE)
        self.logger.info('Configured QOS. Beginning processing loop')

        try:
            while True:
                await asyncio.sleep(1)

        except asyncio.CancelledError:
            pass

    async def amqp_callback(self, channel, body, envelope, properties):
        self.logger.debug("DLR_DATA {0}".format(body))
        data = json.loads(body)

        if 'id' not in data:
            self.logger.warning('DLR does not contain ID field, skipping')
            await channel.basic_client_ack(envelope.delivery_tag)
            return

        self.logger.info('Processing DLR {0}'.format(data['id']))

        if 'url' not in data:
            self.logger.warning('JSON payload missing URL field, skipping')
            await channel.basic_client_ack(envelope.delivery_tag)
            return
        if 'method' not in data:
            self.logger.warning('JSON payload missing HTTP method field, skipping')
            await channel.basic_client_ack(envelope.delivery_tag)
            return

        # So by this point we have enough data to do something
        method = data['method']
        url = data['url']
        retries = int(data.get('retries', '0'))

        # Create POST payload, remove operational fields
        payload = data.copy()
        del payload['url']
        del payload['method']
        del payload['retries']

        if method == 'GET':
            kwargs = {'params': payload}
        else:
            kwargs = {'json': payload}

        try:
            # Attemp to do POST/GET
            async with self.http_session.request(method, url, **kwargs) as resp:
                # If If we have a decent looking status code
                if 200 <= resp.status < 400:
                    # Ack and quit
                    await channel.basic_client_ack(envelope.delivery_tag)
                    self.logger.info('Successfully posterd DLR {0}'.format(data['id']))
                    return

                # 422 is too many requests, retry
                elif resp.status == 422:
                    self.logger.warning('{0} returned 422, retrying'.format(data['id']))
                else:
                    self.logger.warning('Got unknown status code {0}, retrying'.format(resp.status))

        except Exception as err:
            self.logger.exception('Caught exception whilst trying to post DLR', exc_info=err)

        retries += 1

        if retries > RETRY_COUNT:
            self.logger.warning('Have retried {0} times, skipping'.format(RETRY_COUNT))
        else:
            data['retries'] = retries
            payload = json.dumps(data)
            try:
                await self.amqp_channel.basic_publish(payload=payload, exchange_name='', routing_key=DLR_QUEUE)
            except Exception as err:
                self.logger.exception('Caught exception whilst trying to republish DLR', exc_info=err)

        try:
            await channel.basic_client_ack(envelope.delivery_tag)
        except Exception as err:
            self.logger.exception('Caught exception whilst trying to ack DLR', exc_info=err)


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

    dlr_poster = DLRPoster(config, logger)
    await dlr_poster.setup()
    try:
        await dlr_poster.run()
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        await dlr_poster.close()


asyncio.get_event_loop().run_until_complete(main())
