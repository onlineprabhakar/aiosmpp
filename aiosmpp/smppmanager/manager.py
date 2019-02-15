import argparse
import asyncio
import base64
import logging
import json
import pickle
import os
import sys
import uuid
from typing import Optional, Dict, Tuple, Any, List, Type

import aioredis

from aiosmpp.config.smpp import SMPPConfig
from aiosmpp.client import SMPPClientProtocol, SMPPConnectionState
from aiosmpp.pdu import Status, TLV
from aiosmpp import constants as c
from aiosmpp.utils import parse_dlr_text

from aiosmpp.sqs import SQSManager, AWSSQSManager, QueueNotFound


def try_format(value, func, default=None, warn_str=None, allow_none=False):
    if allow_none and value is None:
        return value

    try:
        value = func(value)
    except Exception:
        if warn_str:
            print(warn_str.format(value=value))
        value = default
    return value


class SMPPConnector(object):
    def __init__(self, smpp_config: Dict[str, Any], base_config: SMPPConfig, redis=None, loop: Optional[asyncio.AbstractEventLoop] = None,
                 logger: Optional[logging.Logger] = None, sqs_class: Type[SQSManager] = AWSSQSManager):
        self.config = smpp_config
        self._all_config = base_config
        self._smpp_proto: SMPPClientProtocol = None

        self.logger = logger
        if not logger:
            self.logger = logging.getLogger()

        self._sqs = sqs_class(base_config, self.logger)
        self._sqs_receiver: asyncio.Future = None

        self._queue_name = smpp_config['queue_name']
        self._redis = redis

        self._loop = loop
        if not loop:
            self._loop = asyncio.get_event_loop()

        self._do_reconnect_future = None

    def __del__(self):
        self.close()

    # TODO make this async
    def close(self):
        self._smpp_close()

        try:
            if self._sqs_receiver:
                self._sqs_receiver.cancel()
        except:  # noqa: E722
            pass

    def _smpp_close(self):
        try:
            self._smpp_proto.close()
        except Exception:
            pass
        self._smpp_proto = None
        try:
            if self._do_reconnect_future:
                self._do_reconnect_future.cancel()
        except:  # noqa: E722
            pass

    @property
    def state(self) -> SMPPConnectionState:
        if self._smpp_proto:
            return self._smpp_proto.state
        return SMPPConnectionState.CLOSED

    async def run(self):
        try:
            # Connect and listen to queue
            await self._do_queue_connect()

            # Try and connect to the smpp server
            await self._do_smpp_connect_or_retry()

            while True:
                # print('sleeping')
                await asyncio.sleep(10)
        except asyncio.CancelledError:
            pass

    async def _do_queue_connect(self):
        try:
            self.logger.info('Attempting to create Queues')
            await self._sqs.setup()
            await self._sqs.create_queue(self._queue_name)
            self.logger.info('Created queue {0}'.format(self._queue_name))
            await self._sqs.create_queue(self.config['dlr_queue_name'])
            self.logger.info('Created queue {0}'.format(self.config['dlr_queue_name']))
            await self._sqs.create_queue(self.config['mo_queue_name'])

            self._sqs_receiver = asyncio.ensure_future(self._sqs_recv_loop())
            self.logger.info('Set up SES Poll loop')
        except asyncio.CancelledError:
            raise
        except Exception as err:
            self.logger.exception('Unexpected error when trying to connect to MQ', exc_info=err)

    async def _sqs_recv_loop(self):
        while True:
            try:
                to_delete = []

                for message in await self._sqs.receive_messages(self._queue_name):
                    msg_id = message['MessageId']
                    receipt_handle = message['ReceiptHandle']
                    ack = False

                    try:
                        payload = json.loads(message['Body'])
                    except ValueError as err:
                        self.logger.exception('SMPP Event on MQ is not valid json', exc_info=err)
                        ack = True
                    except Exception as err:
                        self.logger.exception('Unknown error occurned during SQS receive', exc_info=err)
                        # ack = True
                    else:
                        # We've decoded event
                        req_id = payload.get('req_id', 'UNKNOWN_ID')

                        if not payload.get('pdus', []):
                            self.logger.error('{0} | SMPP Event doesnt have any PDUs'.format(req_id))
                            ack = True

                        src_addr = payload['pdus'][0]['source_addr']
                        dest_addr = payload['pdus'][0]['destination_addr']

                        self.logger.info('{0} | Processing SMPP Request {1} -> {2}'.format(req_id, src_addr, dest_addr))

                        try:
                            await self.send_pdus(payload)
                            ack = True
                        except Exception as err:
                            self.logger.exception('Caught exception whilst sending PDUs {0}'.format(err), exc_info=err)

                    if ack:
                        to_delete.append({'Id': msg_id, 'ReceiptHandle': receipt_handle})
                    else:
                        self.logger.warning('Message {0} not ack\'d, it\'ll get redelivered'.format(self.logger))

                if to_delete:
                    await self._sqs.delete_messages(self._queue_name, to_delete)
                    self.logger.info('Removed {0} messages'.format(len(to_delete)))

                self.logger.info('Completed SQS loop')
            except QueueNotFound:
                self.logger.error('SQS queue {0} not found'.format(self._queue_name))
                await asyncio.sleep(5)

            except asyncio.CancelledError:
                break
            except Exception as err:
                self.logger.exception('Caught exception during SES Loop', exc_info=err)

    async def send_pdus(self, event: Dict[str, Any]):
        # DLR will come on the last PDU

        last_pdu = len(event['pdus']) - 1
        has_dlr = 'dlr' in event and event['dlr']

        for index, pdu in enumerate(event['pdus']):
            result = await self._smpp_proto.send_submit_sm(timeout=0.5, **pdu)

            if result['status'] != 0:
                self.logger.warning('Failed to send submit_sm, {0}'.format(result))
                # TODO DEAL WITH ERROR/FAIL
                # If DLR put on redis

                break

            else:
                self.logger.info('Sent submit_sm, message id: {0}'.format(result['payload']['message_id']))

            if has_dlr and index == last_pdu:
                redis_payload = event['dlr'].copy()
                redis_payload['id'] = event['req_id']
                redis_payload = json.dumps(redis_payload)
                msg_id = result['payload']['message_id']

                try:
                    await self._redis.set(msg_id, redis_payload, expire=self.config['dlr_expiry'])
                except Exception as err:
                    self.logger.exception('Failed to put msgid + dlr info into redis', exc_info=err)
                else:
                    # If level 1 or 3, send a DLR when the SMSC accepts message
                    if event['dlr']['level'] in (1, 3):
                        try:
                            text_status = Status(result['status']).name
                        except Exception:
                            self.logger.critical('Status {0} unknown'.format(result['status']))
                            text_status = str(result['status'])

                        dlr_payload = {
                            'id': event['req_id'],
                            'connector': event['connector'],
                            'level': event['dlr']['level'],
                            'method': event['dlr']['method'],
                            'url': event['dlr']['url'],
                            'message_status': text_status,

                            'retries': 0
                        }

                        dlr_payload = json.dumps(dlr_payload)

                        try:
                            await self._sqs.send_message(self.config['dlr_queue_name'], dlr_payload)
                            self.logger.info('Pushed DLR {0} to queue {1}'.format(event['req_id'],
                                                                                  self.config['dlr_queue_name']))
                        except Exception as err:
                            self.logger.exception('Failed to publish DLR to queue {0}'.format(
                                self.config['dlr_queue_name']), exc_info=err)

    async def _do_smpp_reconnect(self):
        try:
            if self.config['conn_loss_retry']:
                # Do reconnect if config says yes
                await asyncio.sleep(self.config['conn_loss_delay'])
                await self._do_smpp_connect_or_retry()
        except asyncio.CancelledError:
            pass

    async def _do_smpp_connect_or_retry(self):
        if not self._smpp_proto:
            self.logger.info('Connecting to SMPP server on {0}:{1}'.format(self.config['host'], self.config['port']))
            self._smpp_proto = None

            logger_name = '.'.join((self.logger.name, 'client'))
            try:
                sock, conn = await self._loop.create_connection(
                    lambda: SMPPClientProtocol(config=self.config, loop=self._loop,
                                               logger=logging.getLogger(logger_name)),
                    self.config['host'],
                    self.config['port']
                )

                self._smpp_proto: SMPPClientProtocol = conn
                self._smpp_proto.set_connection_lost_callback(self.connection_lost_trigger)
                self._smpp_proto.set_deliver_sm_callback(self.deliver_sm_trigger)

            except ConnectionRefusedError:
                self._smpp_proto = None
                self.logger.warning('Cant connect to SMPP server {0}:{1}, scheduling retry'.format(
                    self.config['host'], self.config['port']))

                self._do_reconnect_future = asyncio.ensure_future(self._do_smpp_reconnect())

        if self._smpp_proto:
            # If proto is not None but is closed, do reconnect
            if self._smpp_proto.state == SMPPConnectionState.CLOSED:
                self.logger.warning('SMPP connection closed, scheduling retry')
                try:
                    self._smpp_proto.close()
                except Exception:
                    pass
                self._smpp_proto = None
                self._do_reconnect_future = asyncio.ensure_future(self._do_smpp_reconnect())

            # If proto is not None and is connected, do bind
            elif self._smpp_proto.state == SMPPConnectionState.OPEN:
                if self.config['bind_type'] == 'TX':
                    self.logger.critical('BIND TX not supported')
                    raise NotImplementedError()
                elif self.config['bind_type'] == 'RX':
                    self.logger.critical('BIND RX not supported')
                    raise NotImplementedError()
                else:  # TRX
                    self.logger.info('Initiating TRX bind')
                    self._smpp_proto.bind_trx()

    def connection_lost_trigger(self):
        self.logger.warning('SMPP Connection closed, scheduling retry')
        self._smpp_close()
        self._do_reconnect_future = asyncio.ensure_future(self._do_smpp_reconnect())

    def deliver_sm_trigger(self, pkt: Dict[str, Any]):
        self.logger.debug('Got DELIVER_SM')
        esm_class = c.ESMClassInbound(pkt['payload']['esm_class'])

        # ESMClassInbound as SMSC is sending us a deliver_sm/data_sm
        if c.ESMClassInbound.MESSAGE_TYPE_CONTAINS_DELIVERY_ACK in esm_class or \
                c.ESMClassInbound.MESSAGE_TYPE_CONTAINS_MANUAL_ACK in esm_class:
            self.logger.debug('Got Delivery notification')

            dlr_data = parse_dlr_text(pkt['payload']['short_message'])

            if not dlr_data:
                self.logger.warning('Got DLR but couldn\'t parse text {0}'.format(pkt))
            else:
                # Run process function async
                asyncio.ensure_future(self.process_dlr(pkt, dlr_data))

        elif c.ESMClassInbound.MESSAGE_TYPE_DEFAULT == esm_class:
            self.logger.debug('Got SMS-MO')
            asyncio.ensure_future(self.process_mo(pkt))
        else:
            self.logger.warning('ESM_CLASS {0} not handled'.format(pkt['payload']['esm_class']))

    async def process_dlr(self, pkt: Dict[str, Any], dlr_data: Dict[str, Any]):
        try:
            dlr_redis_data = await self._redis.get(dlr_data['id'])
        except Exception as err:
            self.logger.exception('Failed to get msgid + dlr info from redis', exc_info=err)
            return

        if not dlr_redis_data:
            self.logger.warning('Unknown MSG ID {0}, not found in redis'.format(dlr_data['id']))
            return

        dlr_redis_data = json.loads(dlr_redis_data)

        dlr_payload = {
            'id': dlr_redis_data['id'],
            'id_smsc': dlr_data['id'],
            'connector': self.config['connector_name'],
            'level': 3,
            'method': dlr_redis_data['method'],
            'url': dlr_redis_data['url'],
            'message_status': dlr_data['stat'],

            'subdate': dlr_data['sdate'],
            'donedate': dlr_data['ddate'],
            'sub': dlr_data['sub'],
            'dlvrd': dlr_data['dlvrd'],
            'err': dlr_data['err'],
            'text': dlr_data['text'],

            'retries': 0
        }

        dlr_payload = json.dumps(dlr_payload)

        try:
            await self._sqs.send_message(self.config['dlr_queue_name'], dlr_payload)
            self.logger.info('Pushed DLR {0} to queue {1}'.format(dlr_redis_data['id'], self.config['dlr_queue_name']))
        except Exception as err:
            self.logger.exception('Failed to publish DLR to queue {0}'.format(
                self.config['dlr_queue_name']), exc_info=err)

    async def process_mo(self, pkt: Dict[str, Any]):
        # TODO check short_message, message_payload for msg
        message_id = str(uuid.uuid4())
        message: bytes = pkt['payload']['short_message']

        # https://github.com/jookies/jasmin/blob/1708a9469d327291606dc0896480590392c0b9c0/jasmin/managers/listeners.py#L599

        udhi_indicatior_set = False
        esm_class = c.ESMClassInbound(pkt['payload']['esm_class'])

        if c.ESMClassInbound.GSM_FEATURES_UDHI in esm_class:
            udhi_indicatior_set = True

        not_class2 = True
        data_coding = c.DataCoding(pkt['payload']['data_coding'])
        if c.DataCoding.GSM_MESSAGE_CONTROL in data_coding:
            # TODO we need to look at some class 2 stuff here
            # https://github.com/jookies/jasmin/blob/1708a9469d327291606dc0896480590392c0b9c0/jasmin/managers/listeners.py#L614
            raise NotImplementedError()

        split_method = None
        if TLV.sar_msg_ref_num in pkt['payload']['tlvs']:
            split_method = 'sar'
            total_segments = pkt['payload']['tlvs'][TLV.sar_total_segments]
            segment_seqnum = pkt['payload']['tlvs'][TLV.sar_segment_seqnum]
            msg_ref_num = pkt['payload']['tlvs'][TLV.sar_msg_ref_num]
            self.logger.info('Received multipart SMS-MO using SAR: total {0}, num {1}, ref {2}'.format(
                total_segments, segment_seqnum, msg_ref_num))

        elif udhi_indicatior_set and not_class2 and message[:3] == b'\x05\x00\x03':
            split_method = 'udh'
            # UDH has some single byte integers in the header, can just index instead of struct
            total_segments = message[4]
            segment_seqnum = message[5]
            msg_ref_num = message[3]
            message = message[6:]  # Trim off the header
            self.logger.info('Received multipart SMS-MO using UDH: total {0}, num {1}, ref {2}'.format(
                total_segments, segment_seqnum, msg_ref_num))

        if not split_method:
            # We have 1 short sms, non-mulitpart

            mo_payload = {
                'id': message_id,
                'to': pkt['payload']['dest_addr'],
                'from': pkt['payload']['source_addr'],
                'coding': int(data_coding),
                'origin-connector': self.config['connector_name'],
                'msg': base64.b64encode(message).decode(),

                'retries': 0
            }

            mo_payload = json.dumps(mo_payload)

            try:
                await self._sqs.send_message(self.config['mo_queue_name'], mo_payload)
                self.logger.info('Pushed SMS-MO {0} to queue {1}'.format(message_id, self.config['mo_queue_name']))
            except Exception as err:
                self.logger.exception('Failed to publish SMS-MO to queue {0}'.format(
                    self.config['mo_queue_name']), exc_info=err
                )
        else:
            # We have 1/N multipart SMS MO, short that in Redis
            # noinspection PyUnboundLocalVariable
            sms_part_key = 'long_sms:{0}:{1}:{2}'.format(
                self.config['connector_name'], msg_ref_num, pkt['payload']['dest_addr'])

            # noinspection PyUnboundLocalVariable
            sms_part_fields = {
                'message_id': message_id,
                'total_segments': total_segments,
                'msg_ref_num': msg_ref_num,
                'segment_seqnum': segment_seqnum,
                'message': message
            }
            sms_part_fields = pickle.dumps(sms_part_fields)

            try:
                await self._redis.hset(sms_part_key, str(segment_seqnum), sms_part_fields)
                await self._redis.expire(sms_part_key, 300)
            except Exception as err:
                self.logger.exception('Failed to store multipart SMS-MO in redis', exc_info=err)
                return

            # This will look like
            # KEY long_sms:conn1:someopaqueref:447428555444
            # FIELD 1 VALUE pickled_dict
            # FIELD 2 VALUE pickled_dict
            # FIELD 3 VALUE pickled_dict
            # So a hvals of "long_sms:conn1:someopaqueref:447428555444" will return a list of 3 pickled dicts

            if segment_seqnum == total_segments:
                # We "should" have a complete set here.
                try:
                    pickled_data: List[bytes] = await self._redis.hvals(sms_part_key)
                except Exception as err:
                    self.logger.exception('Failed to retrieve multipart SMS-MO parts from redis', exc_info=err)
                    return

                sms_mo_parts = [pickle.loads(item) for item in pickled_data]
                sms_mo_parts.sort(key=lambda item: item['segment_seqnum'])
                actual_parts = len(sms_mo_parts)

                if actual_parts != total_segments:
                    self.logger.error('SMS-MO have received the last multipart segment and am missing parts. '
                                      'Expected segments {0}, actual {1}, key {2}'.format(
                                          total_segments, actual_parts, sms_part_key))
                    # no point dieing here, might as well try and serve the SMS

                # Concatenate the SMS message parts
                concatenated_msg = b''.join([item['message'] for item in sms_mo_parts])

                mo_payload = {
                    'id': message_id,
                    'to': pkt['payload']['dest_addr'],
                    'from': pkt['payload']['source_addr'],
                    'coding': int(data_coding),
                    'origin-connector': self.config['connector_name'],
                    'msg': base64.b64encode(concatenated_msg).decode(),

                    'retries': 0
                }

                mo_payload = json.dumps(mo_payload)

                try:
                    await self._sqs.send_message(self.config['mo_queue_name'], mo_payload)
                    self.logger.info('Pushed SMS-MO {0} to queue {1}'.format(message_id, self.config['mo_queue_name']))
                except Exception as err:
                    self.logger.exception('Failed to publish SMS-MO to queue {0}'.format(
                        self.config['mo_queue_name']), exc_info=err
                    )


class SMPPManager(object):
    def __init__(self, config: Optional[SMPPConfig] = None, loop: asyncio.AbstractEventLoop = None,
                 logger: Optional[logging.Logger] = None):
        self.loop = loop
        if not loop:
            self.loop = asyncio.get_event_loop()

        self.config = config

        self.connectors: Dict[str, Tuple[SMPPConnector, asyncio.Future]] = {}

        self.redis = None

        self.logger = logger
        if not logger:
            self.logger = logging.getLogger()

    async def setup(self):
        self.logger.info('Creating redis pool')
        self.redis = await aioredis.create_redis_pool(
            'redis://{0}:{1}'.format(self.config.redis['host'], self.config.redis['port']),
            db=self.config.redis['db'], minsize=4, maxsize=12)

        pong = await self.redis.ping()
        if pong != b'PONG':
            self.logger.critical('Could not contact redis')
            raise RuntimeError()
        self.logger.info('Created redis pool')

        # Loop through config
        self.logger.info('Loading SMPP connector config')
        for connector_id, connector_data in self.config.connectors.items():
            if connector_data.get('disabled', '0') == '1':
                self.logger.info('Skipping {0} (disabled)'.format(connector_id))
            else:
                self.logger.info('Adding {0}'.format(connector_id))
                await self.add_connector(connector_id, connector_data)

        self.logger.info('Finished loading SMPP config')

    async def teardown(self):
        self.logger.info('Tearing down smpp config')
        for conn, future in self.connectors.values():
            try:
                conn.close()
                future.cancel()
                await future
            except Exception as err:
                self.logger.exception('Caught exception whilst tearing down smpp connection', exc_info=err)

        try:
            self.logger.info('Stopping redis pool')
            self.redis.close()
            await self.redis.wait_closed()
        except Exception as err:
            self.logger.exception('Caught exception whilst tearing down redis', exc_info=err)

    async def add_connector(self, name: str, smpp_config: Dict[str, str]):
        # Value checking
        if smpp_config['bind_type'] not in ('TX', 'RX', 'TRX'):
            print('bind_type ({0}) is not TX, RX, TRX. Setting to TRX'.format(smpp_config['bind_type']))
            smpp_config['bind_type'] = 'TRX'

        logger_name = 'aiosmpp.smppmanager.{0}'.format(smpp_config['logger_name'])

        conn = SMPPConnector(smpp_config=smpp_config, base_config=self.config, logger=logging.getLogger(logger_name), redis=self.redis)
        future = asyncio.ensure_future(conn.run())

        self.connectors[name] = (conn, future)

        # TODO hook up state change trigger


async def main():
    parser = argparse.ArgumentParser(prog='SMPPManager')

    # --config.file
    parser.add_argument('--config.file', help='Config file location')
    parser.add_argument('--config.dynamodb.table', help='DynamoDB config table')
    parser.add_argument('--config.dynamodb.region', help='DynamoDB region')
    parser.add_argument('--config.dynamodb.key', help='DynamoDB key identifying the config entry')

    args = parser.parse_args()

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

    print('Starting SMPP Manager')
    smpp_mgmr = SMPPManager(config=config)
    await smpp_mgmr.setup()

    await asyncio.sleep(120)

if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(main())
