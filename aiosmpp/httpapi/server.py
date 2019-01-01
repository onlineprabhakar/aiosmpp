import asyncio
import argparse
import binascii
import datetime
import logging
import json
import math
import os
import struct
import sys
import uuid
from typing import Dict, Any, Optional, TYPE_CHECKING, Type

from aiohttp import web

from aiosmpp.utils import gsm_encode
from aiosmpp.constants import AddrTON, AddrNPI, ESMClassMode, ESMClassType, PriorityFlag, \
    RegisteredDeliveryReceipt, ReplaceIfPresentFlag, ESMClassGSMFeatures, MoreMessagesToSend
from aiosmpp.config.httpapi import HTTPAPIConfig
from aiosmpp.httpapi.routetable import RouteTable
from aiosmpp.smppmanager.client import SMPPManagerClient
from aiosmpp.log import get_stdout_logger
import aioamqp

if TYPE_CHECKING:
    import multidict


class WebHandler(object):
    def __init__(self,
                 config: Optional[HTTPAPIConfig] = None,
                 logger: Optional[logging.Logger] = None,
                 smppmanagerclientclass: Type[SMPPManagerClient] = SMPPManagerClient,
                 amqp_connect: aioamqp.connect = aioamqp.connect,
                 loop: asyncio.AbstractEventLoop = None):
        self.config = config

        self.logger = logger
        if not logger:
            self.logger = logging.getLogger()

        self.loop = loop
        if not loop:
            self.loop = asyncio.get_event_loop()

        # TODO find smppmanager / put autodiscovery in the class
        self.smpp_manager_client = smppmanagerclientclass(self.config.smpp_client_url, logger=self.logger)
        self.smpp_manager_client_loop = asyncio.ensure_future(self.smpp_manager_client.run(interval=120), loop=self.loop)

        self.route_table = RouteTable(config, connector_dict=self.smpp_manager_client.connectors)

        self._last_long_msg_ref_num = 0
        self._long_content_max_parts = 5
        self._long_content_split = 'udh'  # Either sar or udh

        self._default_smpp_config = {
            'service_type': None,
            'source_addr_ton': AddrTON.NATIONAL,
            'source_addr_npi': AddrNPI.ISDN,
            # 'source_addr',
            'dest_addr_ton': AddrTON.INTERNATIONAL,
            'dest_addr_npi': AddrNPI.ISDN,
            # 'destination_addr',
            'esm_class': (ESMClassMode.STORE_AND_FORWARD, ESMClassType.DEFAULT),
            'protocol_id': None,
            'priority_flag': PriorityFlag.LEVEL_0,
            'schedule_delivery_time': None,
            'validity_period': None,
            'registered_delivery': RegisteredDeliveryReceipt.NO_SMSC_DELIVERY_RECEIPT_REQUESTED,
            'replace_if_present_flag': ReplaceIfPresentFlag.DO_NOT_REPLACE,
            # 'data_coding',
            'sm_default_msg_id': 0,
            # The sm_length parameter is handled by ShortMessageEncoder
            # 'short_message',
        }

        self._amqp_connect = amqp_connect
        self._amqp_transport = None
        self._amqp_protocol = None
        self._amqp_channel = None

    @property
    def next_long_msg_ref_num(self) -> int:
        if self._last_long_msg_ref_num >= 255:
            self._last_long_msg_ref_num = 0

        self._last_long_msg_ref_num += 1
        return self._last_long_msg_ref_num

    def app(self) -> web.Application:
        _app = web.Application()

        _app.add_routes((
            web.get('/api/v1/status', self.handler_api_v1_status),
            web.post('/api/v1/send', self.handler_api_v1_send),
            web.get('/send', self.handler_send)  # Legacy Jasmin SMPP compatible send
        ))

        _app.on_startup.append(self.on_startup)
        _app.on_shutdown.append(self.on_shutdown)

        return _app

    async def on_startup(self, app):
        try:
            self.logger.info('Attempting to contact MQ')
            self._amqp_transport, self._amqp_protocol = await self._amqp_connect(
                host=self.config.mq['host'],
                port=self.config.mq['port'],
                login=self.config.mq['user'],
                password=self.config.mq['password'],
                virtualhost=self.config.mq['vhost'],
                ssl=self.config.mq['ssl'],
                heartbeat=self.config.mq['heartbeat_interval']
            )

            self.logger.info('Connected to MQ on {0}:{1}'.format(self.config.mq['host'], self.config.mq['port']))
            self._amqp_channel = await self._amqp_protocol.channel()
            self.logger.debug('Created MQ channel')
        except Exception as err:
            self.logger.exception('Unexpected error when trying to connect to MQ', exc_info=err)

    async def on_shutdown(self, app):
        try:
            self.smpp_manager_client_loop.cancel()
            await self.smpp_manager_client_loop
            await self.smpp_manager_client.close()
        except Exception as err:
            self.logger.exception('Caught exception whilst tearing down smpp manager client', exc_info=err)

        try:
            await self._amqp_protocol.close()
            self._amqp_transport.close()
        except Exception as err:
            self.logger.exception('Caught exception whilst tearing down amqp class', exc_info=err)

    def _set_config_params_in_pdu(self, pdu: Dict[str, Any]) -> Dict[str, Any]:
        modified_pdu = pdu.copy()

        for key, value in self._default_smpp_config.items():
            if key not in modified_pdu:
                modified_pdu[key] = value

        return modified_pdu

    def _update_config_params_in_pdu(self, pdu: Dict[str, Any], connector_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Take PDU dict, and update any non locked values
        """

        config_update_params = [
            'protocol_id',
            'replace_if_present_flag',
            'dest_addr_ton',
            'source_addr_npi',
            'dest_addr_npi',
            'service_type',
            'source_addr_ton',
            'sm_default_msg_id',
        ]

        locked_params = pdu.get('locked', [])

        for param in config_update_params:
            if param in locked_params:  # Skip locked values
                continue
            if param not in connector_config:  # Skip values not in smpp config
                continue

            for current_pdu in pdu['pdus']:
                current_pdu[param] = connector_config[param]

        return pdu

    def create_submitsm_pdus(self, source_address, destination_address, short_message, data_coding) -> Dict[str, Any]:
        """
        Create PDUs that are JSON compatible
        :param source_address:
        :param destination_address:
        :param short_message:
        :param data_coding:
        :return:
        """

        # Possible data_coding values : 0,1,2,3,4,5,6,7,8,9,10,13,14
        # Set the max short message length depending on the
        # coding (7, 8 or 16 bits)
        if data_coding in [3, 6, 7, 10]:
            # 8 bit coding
            bits = 8
            max_sm_length = 140
            sliced_max_sm_length = max_sm_length - 6
        elif data_coding in [2, 4, 5, 8, 9, 13, 14]:
            # 16 bit coding
            bits = 16
            max_sm_length = 70
            sliced_max_sm_length = max_sm_length - 3
        else:
            # 7 bit coding is the default
            # for data_coding in [0, 1] or any other invalid value
            bits = 7
            max_sm_length = 160
            sliced_max_sm_length = 153

        long_msg = short_message
        if bits == 16:
            sm_length = len(short_message) // 2
        else:
            sm_length = len(short_message)

        result = {
            'pdus': []
        }

        if sm_length > max_sm_length:
            # As the lengths of a message are shorter when its split
            # - dont exceed the configured max parts
            num_parts = min((
                int(math.ceil(sm_length / sliced_max_sm_length)),
                self._long_content_max_parts
            ))

            msg_ref_num = self.next_long_msg_ref_num
            for i in range(0, num_parts):
                sequence_number = i + 1

                if bits == 16:
                    short_message_segment = long_msg[sliced_max_sm_length * i * 2: sliced_max_sm_length * (i + 1) * 2]
                else:
                    short_message_segment = long_msg[sliced_max_sm_length * i: sliced_max_sm_length * (i + 1)]

                current_pdu = {
                    'source_addr': source_address,
                    'destination_addr': destination_address,
                    'data_coding': data_coding,
                    'short_message': short_message_segment
                }

                current_pdu = self._set_config_params_in_pdu(current_pdu)

                # Deal with splitting details
                if self._long_content_split == 'sar':
                    current_pdu['sar_total_segments'] = num_parts
                    current_pdu['sar_segment_seqnum'] = sequence_number
                    current_pdu['sar_msg_ref_num'] = msg_ref_num
                elif self._long_content_split == 'udh':
                    current_pdu['esm_class'] = (ESMClassMode.DEFAULT, ESMClassType.DEFAULT,
                                                ESMClassGSMFeatures.UDHI_INDICATOR_SET)

                    if sequence_number < num_parts:
                        current_pdu['more_messages_to_send'] = MoreMessagesToSend.MORE_MESSAGES
                    else:
                        current_pdu['more_messages_to_send'] = MoreMessagesToSend.NO_MORE_MESSAGES

                    # If we have a binary message, Null short_message and create short_message_hex
                    # As python3 cares about bytes in a string, we need a binary message

                    # If we had a UCS2 message, it will be bytes
                    if isinstance(current_pdu['short_message'], bytes):
                        current_pdu['short_message_hex'] = current_pdu['short_message']
                    elif isinstance(current_pdu['short_message'], str):
                        current_pdu['short_message_hex'] = current_pdu['short_message'].encode()
                    current_pdu['short_message'] = None

                    udh_header = struct.pack('>BBBBBB', 5, 0, 3, msg_ref_num, num_parts, sequence_number)
                    current_pdu['short_message_hex'] = udh_header + current_pdu['short_message_hex']

                    current_pdu['short_message_hex'] = binascii.hexlify(current_pdu['short_message_hex']).decode()

                result['pdus'].append(current_pdu)

        else:
            # Msg didnt need splitting

            current_pdu = {
                'source_addr': source_address,
                'destination_addr': destination_address,
                'data_coding': data_coding,
                'short_message': short_message
            }

            current_pdu = self._set_config_params_in_pdu(current_pdu)

            if isinstance(current_pdu['short_message'], bytes):
                current_pdu['short_message_hex'] = binascii.hexlify(current_pdu['short_message']).decode()
                current_pdu['short_message'] = None

            result['pdus'].append(current_pdu)

        # Append niceties to event
        result['to'] = destination_address
        result['from'] = source_address
        result['timestamp'] = datetime.datetime.now().timestamp()
        result['msg'] = short_message
        result['direction'] = 'MT'

        return result

    def normalise_pdus(self, pdus: Dict[str, Any]):
        for pdu in pdus['pdus']:
            new_esm_class = 0

            for esm_part in pdu['esm_class']:
                new_esm_class |= int(esm_part)
            pdu['esm_class'] = new_esm_class

    @staticmethod
    def parse_legacy_send_post_parameters(form: 'multidict.MultiDict') -> Dict[str, Any]:
        """
        Takes in a multidict from an `await request.post()` and will return a dict

        Required Fields:
        * to - destination address
        * username - Jasmin username - ignored
        * password - Jasmin password - ignored

        Optional Fields:
        * from - originator - default none
        * coding - Values 0 -> 14
        * priority - 0,1,2 or 3 - default 0
        * sdt - scheduled delivery time - default none
        * validity-period - integer - default none
        * dlr - "yes" or "no" - default no
        * dlr-url - http/s URL
        * dlr-level - 1,2 or 3
        * dlr-method - GET/POST
        * tags - comma separated list of integers - default none
        * content - text
        * hex-content - binary hex value

        If `dlr` is `yes` then the other fields starting with `dlr` are required.
        Either `content` or `hex-content` is requied, they are mutually exclusive.

        :raises ValueError: If required parameters are invalid
        """
        if 'to' not in form:
            raise ValueError('to address missing from payload')
        if 'username' not in form:
            raise ValueError('username missing from payload')
        if 'password' not in form:
            raise ValueError('password missing from payload')

        if 'content' not in form and 'hex-content' not in form:
            raise ValueError('content or hex-content must be provided')

        if 'coding' in form and form.get('coding') not in ('0', '1', '2', '3', '4', '5', '6', '7', '8',
                                                           '9', '10', '11', '12', '13', '14'):
            raise ValueError('coding must be in the range 0-14')

        if 'priority' in form and form.get('priority') not in ('0', '1', '2', '3'):
            raise ValueError('priority must be in the range 0-3')

        validity = None
        if 'validity-period' in form:
            try:
                validity = int(form.get('validity-period'))
            except ValueError:
                raise ValueError('validity-period must be an integer')
            else:
                if validity < 0:
                    raise ValueError('validity-period must be greater than 0')

        tags = []
        if 'tags' in form:
            try:
                tags = [int(part) for part in form.get('tags').split(',')]
            except ValueError:
                raise ValueError('tags must be integers')

        dlr_data = {}
        if 'dlr' in form and form.get('dlr', 'no') == 'yes':
            if 'dlr-url' not in form:
                raise ValueError('dlr-url missing')
            if 'dlr-level' not in form:
                raise ValueError('dlr-level missing')
            if 'dlr-method' not in form:
                raise ValueError('dlr-method missing')

            if form.get('dlr-level') not in ('1', '2', '3'):
                raise ValueError('dlr-level not 1,2 or 3')
            if form.get('dlr-method') not in ('GET', 'POST'):
                raise ValueError('dlr-method not GET or POST')

            dlr_data = {
                'url': form.get('dlr-url'),
                'level': int(form.get('dlr-level')),
                'method': form.get('dlr-method')
            }

        content = form.get('content')
        hex_content = form.get('hex-content')
        if content:
            hex_content = None

        result = {
            'to': form['to'],
            'from': form.get('from'),
            'coding': int(form.get('coding', '0')),
            'priority': int(form.get('priority', '0')),
            'sdt': form.get('std'),
            'validity-period': validity,
            'tags': tags,
            'content': content,
            'hex-content': hex_content,
            'dlr': dlr_data
        }

        return result

    async def publish_pdus_to_queue(self, queue_payload: Dict[str, Any], queue_name: str):
        payload = json.dumps(queue_payload)

        await self._amqp_channel.basic_publish(
            payload=payload,
            exchange_name='',
            routing_key=queue_name
        )

    # Legacy send
    async def handler_send(self, request: web.Request) -> web.Response:
        request_id = str(uuid.uuid4())

        # Parse / Validate form data
        try:
            request_dict = self.parse_legacy_send_post_parameters(request.query)
        except ValueError as err:
            return web.Response(text='Error "{0}"'.format(err), status=400)

        self.logger.debug('{0} | Validated POST parameters'.format(request_id))

        # Convert MSG into PDUs and split+UDH if necessary, including all default pdu parameters
        # Add a `locked` field so that applying settings later can ignore some pdu fields
        # ---------------------------------------

        if not request_dict['hex-content']:
            if request_dict['coding'] == 0:
                short_message = gsm_encode(request_dict['content'])
            else:
                short_message = request_dict['content']

        else:
            short_message = binascii.unhexlify(request_dict['hex-content'])

        pdu_event = self.create_submitsm_pdus(
            source_address=request_dict['from'],
            destination_address=request_dict['to'],
            short_message=short_message,
            data_coding=request_dict['coding']
        )
        pdu_event['tags'] = request_dict['tags']
        pdu_event['dlr'] = request_dict['dlr']
        pdu_event['locked'] = []  # Stores the names of locked attributes so they dont get reset to defaults

        self.logger.debug('{0} | Num PDUs to send {1}'.format(request_id, len(pdu_event['pdus'])))

        # TODO Evaluate interceptor table
        # TODO Process active intercept
        # print()

        connector = self.route_table.evaluate(pdu_event)
        if connector is None:
            self.logger.critical('No route found for {0}'.format(request_id))
            return web.Response(body='Error "No route found"', status=412)

        # Re apply some connector level pdu parameters
        pdu_event = self._update_config_params_in_pdu(pdu_event, connector.config)

        # Set DLR params
        if pdu_event['dlr']:
            # Set DLR on last PDU
            pdu_event['pdus'][-1]['registered_delivery'] = RegisteredDeliveryReceipt.SMSC_DELIVERY_RECEIPT_REQUESTED

        # Fixup pdus
        self.normalise_pdus(pdu_event)

        queue_name = connector.queue_name
        queue_payload = {
            'req_id': request_id,
            'connector': connector.name,
            'pdus': pdu_event['pdus'],
            'dlr': pdu_event['dlr']
        }

        self.logger.debug('{0} | Pushing event to queue'.format(request_id))
        await self.publish_pdus_to_queue(queue_payload, queue_name)

        self.logger.info('{0} | Pushed event to queue'.format(request_id))
        return web.Response(body='Success "{0}"'.format(request_id))

    async def handler_api_v1_send(self, request: web.Request) -> web.Response:
        pass

    async def handler_api_v1_status(self, request: web.Request) -> web.Response:
        return web.Response(text='OK', status=200)


def app(argv: list = None) -> web.Application:
    parser = argparse.ArgumentParser(prog='HTTP API')

    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose mode')
    parser.add_argument('--config.file', help='Config file location')
    parser.add_argument('--config.dynamodb.table', help='DynamoDB config table')
    parser.add_argument('--config.dynamodb.region', help='DynamoDB region')
    parser.add_argument('--config.dynamodb.key', help='DynamoDB key identifying the config entry')

    args = parser.parse_args(argv[1:])

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logger = get_stdout_logger('httpclient', log_level)
    conf_logger = get_stdout_logger('httpclient.config', log_level)

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

    web_server = WebHandler(config=config, logger=logger)
    return web_server.app()


if __name__ == '__main__':
    print('Running on 0.0.0.0:8080')
    web.run_app(app(sys.argv), print=lambda x: None)
