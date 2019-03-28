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
RETRY_COUNT = 10  # Means max exponential backoff is 1024, will me min'd to sqs's 900


class MOPoster(object):
    def __init__(self, config: SMPPConfig, logger: logging.Logger, sqs_class: Type[SQSManager] = AWSSQSManager):
        self.logger = logger
        self.config = config

        self._sqs = sqs_class(config=config)
        self._sqs_receiver: asyncio.Future = None

        self.http_session: aiohttp.ClientSession = None

    async def close(self):
        self.logger.info('Stopping MO Poster')
        await self.http_session.close()
        await self._sqs.close()
        self.logger.info('Tore down MO Poster connections')

    async def setup(self):
        self.logger.info('Starting MO Poster setup')
        await self._sqs.setup()
        await self._sqs.create_queue(self.config.mo_queue)
        self.logger.info('Finished SQS setup')

        # TODO make configurable
        timeout = aiohttp.ClientTimeout(total=2)
        connector = aiohttp.TCPConnector(verify_ssl=False)
        self.http_session = aiohttp.ClientSession(connector=connector, timeout=timeout)
        self.logger.info('Finished MO Poster setup')

    async def run(self):
        while True:
            try:
                coros = []
                to_delete = []

                # TODO add some dodgy logic here so that we can delay messages greater than 15min
                # i.e not_before field which contains future timestamp, so you can shortcut the function and put back on queue
                # as cumulative time of exponential backoff to 10 is around 30ish minutes, ideally i'd like to make the attempt
                # number configurable and allow upto 6h of backoff (gives me enough time to wake up and fix things)

                for message in await self._sqs.receive_messages(self.config.mo_queue, max_messages=10):
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
                        coros.append(self._process_mo(payload, msg_id, receipt_handle))

                results = await asyncio.gather(*coros)
                # Sort through the results and keep any that [0] is True
                to_delete.extend([{'Id': res[1], 'ReceiptHandle': res[2]} for res in results if res[0]])

                if to_delete:
                    await self._sqs.delete_messages(self.config.mo_queue, to_delete)
                    self.logger.info('Removed {0} messages'.format(len(to_delete)))

                self.logger.info('Completed SQS loop')

            except asyncio.CancelledError:
                break
            except Exception as err:
                logging.exception('Caught exception during SQS Loop', exc_info=err)

    async def _process_mo(self, data: dict, msg_id: str, receipt_handle: str) -> Tuple[bool, str, str]:
        self.logger.debug("MO_DATA {0}".format(data))

        if 'id' not in data:
            self.logger.warning('MO does not contain ID field, skipping')
            return False, msg_id, receipt_handle

        self.logger.info('Processing MO {0} {1}'.format(data['id'], data['message_status']))
        # {
        #   "id": "141f0bce-8e2c-43d8-af90-06ff3b1b28ef",
        #   "to": "447222222222",
        #   "from": "447111111111",
        #   "coding": 0,
        #   "origin-connector":
        #   "smpp_conn1",
        #   "msg": "SGVsbG8=",
        #   "retries": 0
        # }

        # TODO msg decoding based on coding value, aka gsm7, utf 16 -> bin etc...

        # TODO mo_route_table
        route = self.config.mo_routes['0']
        retries = int(data.get('retries', '0'))
        url = route['url']

        # Create POST payload, remove operational fields
        payload = data.copy()
        del payload['retries']

        if route['response_type'] == 'json':
            kwargs = {'url': url, 'json': payload}
        else:  # Form
            kwargs = {'url': url, 'data': payload}

        try:
            # Attemp to do POST/GET
            async with self.http_session.post(**kwargs) as resp:
                # If If we have a decent looking status code
                if 200 <= resp.status < 400:
                    # Ack and quit
                    self.logger.info('Successfully posterd MO {0}'.format(data['id']))
                    return True, msg_id, receipt_handle

                # 422 is too many requests, retry
                elif resp.status == 422:
                    self.logger.warning('{0} returned 422, retrying'.format(data['id']))
                else:
                    self.logger.warning('Got unknown status code {0}, retrying'.format(resp.status))
        except aiohttp.client_exceptions.ClientConnectorError:
            self.logger.warning('Failed to connect to {0}'.format(url))
        except Exception as err:
            self.logger.exception('Caught exception whilst trying to post MO', exc_info=err)

        retries += 1

        if retries > RETRY_COUNT:
            self.logger.warning('Have retried {0} times, skipping'.format(RETRY_COUNT))
        else:
            data['retries'] = retries
            payload = json.dumps(data)

            exp_backoff = 2**retries

            try:
                await self._sqs.send_message(self.config.mo_queue, payload, delay_seconds=exp_backoff)
            except Exception as err:
                self.logger.exception('Caught exception whilst trying to republish MO', exc_info=err)

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
    logger = get_stdout_logger('moposter', log_level)
    conf_logger = get_stdout_logger('moposter.config', log_level)

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

        config = await SMPPConfig.from_file(filepath, logger=conf_logger)

    mo_poster = MOPoster(config, logger)
    await mo_poster.setup()
    try:
        await mo_poster.run()
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        await mo_poster.close()


asyncio.get_event_loop().run_until_complete(main())
