import asyncio
import logging
import hashlib
import uuid
from typing import List

from aiosmpp.config.smpp import SMPPConfig

import aioboto3


class QueueNotFound(Exception):
    pass


class SQSManager(object):
    def __init__(self, config: SMPPConfig, logger: logging.Logger = None):
        self.logger = logger
        if not logger:
            self.logger = logging.getLogger('aiosmpp.sqs')
        self._config = config
        self._sqs_client = None

        self._queue_map = {}

    async def setup(self):
        pass

    async def close(self):
        pass

    async def create_smpp_queues(self):
        pass

    async def send_message(self, queue: str, msg: str, retries: int = 3, delay_seconds: int = 0):
        pass

    async def receive_messages(self, queue: str, max_messages: int = 5, wait_time: int = 20) -> List[dict]:
        return []

    async def delete_messages(self, queue: str, message_ids: List[dict]):
        pass

    async def create_queue(self, queue_name: str):
        pass


class MockSQSManager(SQSManager):
    async def send_message(self, queue: str, msg: str, retries: int = 3, delay_seconds: int = 0):
        if queue not in self._queue_map:
            self._queue_map[queue] = []

        self._queue_map[queue].append({'MessageId': uuid.uuid4().hex, 'ReceiptHandle': uuid.uuid4().hex, 'Body': msg})

    async def receive_messages(self, queue: str, max_messages: int = 5, wait_time: int = 20) -> List[dict]:
        if queue not in self._queue_map:
            return []

        items = self._queue_map[queue]
        self._queue_map[queue].clear()
        return items

    async def delete_messages(self, queue: str, message_ids: List[dict]):
        if queue in self._queue_map:
            items_to_remove = [item for item in self._queue_map[queue] if item['MessageId'] in message_ids]
            for item in items_to_remove:
                self._queue_map[queue].remove(item)

    async def create_queue(self, queue_name: str):
        if queue_name not in self._queue_map:
            self._queue_map[queue_name] = []


class AWSSQSManager(SQSManager):
    def __init__(self, *args, **kwargs):
        super(AWSSQSManager, self).__init__(*args, **kwargs)

        self._QueueDoesNotExist = QueueNotFound

    async def setup(self):
        endpoint_url = self._config.mq['aws_endpoint']

        # if endpoint url is set and starts with http, we want to disable https
        use_ssl = False if endpoint_url and not endpoint_url.startswith('https') else True
        client_kwargs = {'region_name': self._config.mq['region'], 'endpoint_url': endpoint_url, 'use_ssl': use_ssl}
        self._sqs_client = aioboto3.client('sqs', **client_kwargs)
        self._QueueDoesNotExist = self._sqs_client.exceptions.QueueDoesNotExist

        await self.get_queues()

    async def get_queues(self):
        kwargs = {} if not self._config.mq['name_prefix'] else {'QueueNamePrefix': self._config.mq['name_prefix']}
        resp = await self._sqs_client.list_queues(**kwargs)

        for url in resp.get('QueueUrls', []):
            name = url.rsplit('/', 1)[-1]
            self._queue_map[name] = url

    async def create_smpp_queues(self):
        """
        Called by HTTP api to create queues to put PDU's on
        """
        for conn_name, conn_data in self._config.connectors.items():
            if conn_data['queue_name'] in self._queue_map:
                continue

            await self.create_queue(conn_data['queue_name'])

    async def create_queue(self, queue_name: str):
        self.logger.info('Creating Queue {0}'.format(queue_name))
        try:
            if queue_name.endswith('.fifo'):
                kwargs = {'Attributes': {'FifoQueue': 'true'}}
            else:
                kwargs = {}

            try:
                resp = await self._sqs_client.create_queue(QueueName=queue_name, **kwargs)
            except self._sqs_client.exceptions.QueueDeletedRecently:
                self.logger.warning('Queue {0} was deleted recently, waiting 70 seconds before trying again'.format(queue_name))
                # Amazon requirement of 60s wait
                await asyncio.sleep(70)
                resp = await self._sqs_client.create_queue(QueueName=queue_name, **kwargs)

            self._queue_map[queue_name] = resp['QueueUrl']
            self.logger.info('Created Queue {0}'.format(queue_name))
        except Exception as err:
            self.logger.exception('Caught exception whilst trying to create SQS queue {0}'.format(queue_name),
                                  exc_info=err, extra={'stack': True})

    async def close(self):
        await self._sqs_client.close()

    async def send_message(self, queue: str, msg: str, retries: int = 3, delay_seconds: int = 0):
        try:
            queue_url = self._queue_map[queue]
        except KeyError:
            raise QueueNotFound('Failed to find queue url for {0}'.format(queue))

        attempt = 0

        # Force it to 0 if a fifo queue
        delay_seconds = min([delay_seconds, 900])

        while attempt < retries:
            try:
                kwargs = {
                    'QueueUrl': queue_url,
                    'MessageBody': msg,
                }
                if queue.endswith('.fifo'):
                    kwargs['MessageDeduplicationId'] = hashlib.md5(msg.encode()).hexdigest()
                    kwargs['MessageGroupId'] = queue
                    # DelaySeconds is queue-wide when using fifo
                else:
                    kwargs['DelaySeconds'] = delay_seconds

                resp = await self._sqs_client.send_message(**kwargs)
                self.logger.info('Submitted message {0} {1} to {2}'.format(resp['MessageId'], resp.get('SequenceNumber', ''), queue))
                break
            except Exception as err:
                self.logger.exception('Failed to push message to queue {0}, attempt: {1}'.format(queue, attempt),
                                      exc_info=err, extra={'stack': True})
            attempt += 1
        else:
            raise Exception('Failed to put message in {0} tries'.format(attempt))

    async def receive_messages(self, queue: str, max_messages: int = 5, wait_time: int = 20) -> List[dict]:
        # Limits imposed by amazon
        max_messages = min([max_messages, 10])
        wait_time = min([wait_time, 20])

        try:
            queue_url = self._queue_map[queue]
        except KeyError:
            raise QueueNotFound('Failed to find queue url for {0}'.format(queue))

        try:
            resp = await self._sqs_client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=max_messages,
                WaitTimeSeconds=wait_time
            )
            messages = resp.get('Messages', [])

        except asyncio.CancelledError:
            raise
        except self._QueueDoesNotExist:
            raise QueueNotFound('Queue {0} does not exist in SQS, if it has just been created, it will take some time'.format(queue))
        except Exception as err:
            self.logger.exception('Failed to receive messages from {0}'.format(queue), exc_info=err)
            messages = []

        return messages

    async def delete_messages(self, queue: str, message_ids: List[dict]):
        try:
            queue_url = self._queue_map[queue]
        except KeyError:
            raise QueueNotFound('Failed to find queue url for {0}'.format(queue))

        try:
            resp = await self._sqs_client.delete_message_batch(QueueUrl=queue_url, Entries=message_ids)
            if 'Failed' in resp:
                self.logger.warning('SQS failed to delete the following from {0}, {1}'.format(queue, resp['Failed']))
        except asyncio.CancelledError:
            raise
        except Exception as err:
            self.logger.exception('Failed to delete messages from {0}'.format(queue), exc_info=err)
