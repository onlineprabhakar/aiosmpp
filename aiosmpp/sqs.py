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

    async def send_message(self, queue: str, msg: str, retries: int = 3):
        pass

    async def receive_messages(self, queue: str) -> List[dict]:
        return []

    async def delete_messages(self, queue: str, message_ids: List[dict]):
        pass


class MockSQSManager(SQSManager):
    async def send_message(self, queue: str, msg: str, retries: int = 3):
        if queue not in self._queue_map:
            self._queue_map[queue] = []

        self._queue_map[queue].append({'MessageId': uuid.uuid4().hex, 'ReceiptHandle': uuid.uuid4().hex, 'Body': msg})

    async def receive_messages(self, queue: str) -> List[dict]:
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


class AWSSQSManager(SQSManager):
    async def setup(self):
        endpoint_url = self._config.mq['aws_endpoint']

        # if endpoint url is set and starts with http, we want to disable https
        use_ssl = False if endpoint_url and not endpoint_url.startswith('https') else True
        client_kwargs = {'region_name': self._config.mq['region'], 'endpoint_url': endpoint_url, 'use_ssl': use_ssl}
        self._sqs_client = aioboto3.client('sqs', **client_kwargs)

    async def create_smpp_queues(self):
        """
        Called by HTTP api to create queues to put PDU's on
        """
        kwargs = {} if not self._config.mq['name_prefix'] else {'QueueNamePrefix': self._config.mq['name_prefix']}
        resp = await self._sqs_client.list_queues(**kwargs)

        for url in resp.get('QueueUrls', []):
            name = url.rsplit('/', 1)[-1]
            self._queue_map[name] = url

        for conn_name, conn_data in self._config.connectors.items():
            queue_name = conn_data['queue_name']
            use_fifo = self._config.mq['use_fifo']
            if queue_name in self._queue_map:
                continue

            self.logger.info('Creating Queue {0}'.format(queue_name))
            try:
                kwargs = {'Attributes': {'FifoQueue': str(use_fifo).lower()}}
                resp = await self._sqs_client.create_queue(QueueName=queue_name, **kwargs)
                self._queue_map[queue_name] = resp['QueueUrl']
                self.logger.info('Created Queue {0}'.format(queue_name))
            except Exception as err:
                self.logger.exception('Caught exception whilst trying to create SQS queue {0}'.format(queue_name),
                                      exc_info=err, extra={'stack': True})

    async def close(self):
        await self._sqs_client.close()

    async def send_message(self, queue: str, msg: str, retries: int = 3):
        try:
            queue_url = self._queue_map[queue]
        except KeyError:
            raise QueueNotFound('Failed to find queue url for {0}'.format(queue))

        attempt = 0
        while attempt < retries:
            try:
                await self._sqs_client.send_message(
                    QueueUrl=queue_url,
                    MessageBody=msg,
                    MessageDeduplicationId=hashlib.md5(msg.encode()).hexdigest(),
                    MessageGroupId=queue
                )
                break
            except Exception as err:
                self.logger.exception('Failed to push message to queue {0}, attempt: {1}'.format(queue, attempt),
                                      exc_info=err, extra={'stack': True})
            attempt += 1
        else:
            raise Exception('Failed to put message in {0} tries'.format(attempt))

    async def receive_messages(self, queue: str) -> List[dict]:
        try:
            queue_url = self._queue_map[queue]
        except KeyError:
            raise QueueNotFound('Failed to find queue url for {0}'.format(queue))

        try:
            resp = await self._sqs_client.receive_message(
                QueueUrl=queue_url,
                WaitTimeSeconds=60
            )
            messages = resp.get('Messages', [])

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
        except Exception as err:
            self.logger.exception('Failed to delete messages from {0}'.format(queue), exc_info=err)
