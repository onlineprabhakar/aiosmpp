import asyncio
import argparse
import logging
import sys
import os
import json
from typing import Type, Tuple

import aiohttp
from aiosmpp.config.smpp import SMPPConfig
from aiosmpp.log import get_stdout_logger
from aiosmpp.sqs import SQSManager, AWSSQSManager


# TODO make configurable
RETRY_COUNT = 5


class DLRPoster(object):
    def __init__(self, config: SMPPConfig, logger: logging.Logger, sqs_class: Type[SQSManager] = AWSSQSManager):
        self.logger = logger
        self.config = config

        self._sqs = sqs_class(config=config)
        self._sqs_receiver: asyncio.Future = None

        self.http_session: aiohttp.ClientSession = None

    async def close(self):
        self.logger.info('Stopping DLR Poster')
        await self.http_session.close()
        await self._sqs.close()
        self.logger.info('Tore down DLR Poster connections')

    async def setup(self):
        self.logger.info('Starting DLR Poster setup')
        await self._sqs.setup()
        await self._sqs.create_queue(self.config.dlr_queue)
        self.logger.info('Finished SQS setup')

        # TODO make configurable
        timeout = aiohttp.ClientTimeout(total=2)
        connector = aiohttp.TCPConnector(verify_ssl=False)
        self.http_session = aiohttp.ClientSession(connector=connector, timeout=timeout)
        self.logger.info('Finished DLR Poster setup')

    async def run(self):
        while True:
            try:
                coros = []
                to_delete = []

                for message in await self._sqs.receive_messages(self.config.dlr_queue):
                    msg_id = message['MessageId']
                    receipt_handle = message['ReceiptHandle']

                    try:
                        payload = json.loads(message['Body'])
                    except ValueError as err:
                        self.logger.exception('SMPP Event on MQ is not valid json', exc_info=err)
                        to_delete.append({'Id': msg_id, 'ReceiptHandle': receipt_handle})
                    except Exception as err:
                        self.logger.exception('Unknown error occurned during SQS receive', exc_info=err)
                        # ack = True
                    else:
                        # We've decoded event
                        # TODO do all the _process_dlr in parallel
                        coros.append(self._process_dlr(payload, msg_id, receipt_handle))

                results = await asyncio.gather(*coros)
                # Sort through the results and keep any that [0] is True
                to_delete.extend([{'Id': res[1], 'ReceiptHandle': res[2]} for res in results if res[0]])

                if to_delete:
                    await self._sqs.delete_messages(self.config.dlr_queue, to_delete)
                    self.logger.info('Removed {0} messages'.format(len(to_delete)))

                self.logger.info('Completed SQS loop')

            except asyncio.CancelledError:
                break
            except Exception as err:
                logging.exception('Caught exception during SES Loop', exc_info=err)

    async def _process_dlr(self, data: dict, msg_id: str, receipt_handle: str) -> Tuple[bool, str, str]:
        self.logger.debug("DLR_DATA {0}".format(data))

        if 'id' not in data:
            self.logger.warning('DLR does not contain ID field, skipping')
            return False, msg_id, receipt_handle

        self.logger.info('Processing DLR {0}'.format(data['id']))

        if 'url' not in data:
            self.logger.warning('JSON payload missing URL field, skipping')
            return False, msg_id, receipt_handle
        if 'method' not in data:
            self.logger.warning('JSON payload missing HTTP method field, skipping')
            return False, msg_id, receipt_handle

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
                    self.logger.info('Successfully posterd DLR {0}'.format(data['id']))
                    return True, msg_id, receipt_handle

                # 422 is too many requests, retry
                elif resp.status == 422:
                    self.logger.warning('{0} returned 422, retrying'.format(data['id']))
                else:
                    self.logger.warning('Got unknown status code {0}, retrying'.format(resp.status))
        except aiohttp.client_exceptions.ClientConnectorError:
            self.logger.warning('Failed to connect to {0}'.format(url))
        except Exception as err:
            self.logger.exception('Caught exception whilst trying to post DLR', exc_info=err)

        retries += 1

        if retries > RETRY_COUNT:
            self.logger.warning('Have retried {0} times, skipping'.format(RETRY_COUNT))
        else:
            data['retries'] = retries
            payload = json.dumps(data)
            try:
                await self._sqs.send_message(self.config.dlr_queue, payload)
            except Exception as err:
                self.logger.exception('Caught exception whilst trying to republish DLR', exc_info=err)

        return True, msg_id, receipt_handle


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

        config = SMPPConfig.from_file(filepath, logger=conf_logger)

    dlr_poster = DLRPoster(config, logger)
    await dlr_poster.setup()
    try:
        await dlr_poster.run()
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        await dlr_poster.close()


asyncio.get_event_loop().run_until_complete(main())
