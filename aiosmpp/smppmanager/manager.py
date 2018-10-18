import argparse
import asyncio
import os
import sys
from typing import Optional, Dict, Tuple, Any

from slugify import slugify

from aiosmpp.config.smpp import SMPPConfig
from aiosmpp.client import SMPPClientProtocol, SMPPConnectionState
import aioamqp
from aioamqp.channel import Channel as AMQPChannel



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
    def __init__(self, config: Dict[str, Any], loop: Optional[asyncio.AbstractEventLoop]=None):
        self.config = config
        self._smpp_proto: SMPPClientProtocol = None

        self._amqp_transport = None
        self._amqp_protocol: aioamqp.AmqpProtocol = None
        self._amqp_channel: AMQPChannel = None
        self._queue_name = config['queue_name']

        self._loop = loop
        if not loop:
            self._loop = asyncio.get_event_loop()

        self._do_reconnect_future = None

    def __del__(self):
        self.close()

    def close(self):
        try:
            self._smpp_proto.close()
        except Exception:
            pass
        self._smpp_proto = None
        try:
            if self._do_reconnect_future:
                self._do_reconnect_future.cancel()
        except:
            pass

        try:
            if self._amqp_transport:
                self._amqp_transport.close()
        except:
            pass

    @property
    def state(self) -> SMPPConnectionState:
        if self._smpp_proto:
            return self._smpp_proto.state
        return SMPPConnectionState.CLOSED

    async def run(self):
        # Connect and listen to queue
        await self._do_queue_connect()

        # Try and connect to the smpp server
        await self._do_smpp_connect_or_retry()

        while True:
            # print('sleeping')
            await asyncio.sleep(10)

    async def _do_queue_connect(self):
        try:

            print('Attempting to contact MQ')
            self._amqp_transport, self._amqp_protocol = await aioamqp.connect(
                host=self.config['mq']['host'],
                port=self.config['mq']['port'],
                login=self.config['mq']['user'],
                password=self.config['mq']['password'],
                virtualhost=self.config['mq']['vhost'],
                ssl=False,
                heartbeat=self.config['mq']['heartbeat_interval']
            )
            print('Connected to MQ on {0}:{1}'.format(self.config['mq']['host'], self.config['mq']['port']))
            self._amqp_channel = await self._amqp_protocol.channel()
            print('Created MQ channel')

            # Declare queue
            await self._amqp_channel.queue_declare(self._queue_name, durable=True)
            print('Declared MQ channel {0}'.format(self._queue_name))
            # Setup QOS so we only take 1 msg at a time
            await self._amqp_channel.basic_qos(prefetch_count=1, prefetch_size=0, connection_global=False)
            print('Set MQ QOS Settings')

            await self._amqp_channel.basic_consume(self._amqp_callback, queue_name=self._queue_name)
            print('Set up callback')
        except Exception as err:
            print('Unexpected error when trying to connect to MQ: {0}'.format(repr(err)))

    async def _amqp_callback(self, channel, body, envelope, properties):
        print(" [x] Received {0}".format(body))
        await asyncio.sleep(1)
        print(" [x] Done")
        await channel.basic_client_ack(delivery_tag=envelope.delivery_tag)
        print(" [x] Ackd")

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
            self._smpp_proto = None
            try:
                sock, conn = await self._loop.create_connection(
                    lambda: SMPPClientProtocol(config=self.config, loop=self._loop),
                    self.config['host'],
                    self.config['port']
                )

                self._smpp_proto = conn
                self._smpp_proto.set_connection_lost_callback(self.connection_lost_trigger)

            except ConnectionRefusedError:
                self._smpp_proto = None
                print('Cant connect to {0}:{1}, retrying'.format(self.config['host'], self.config['port']))

                self._do_reconnect_future = asyncio.ensure_future(self._do_smpp_reconnect())

        if self._smpp_proto:
            # If proto is not None but is closed, do reconnect
            if self._smpp_proto.state == SMPPConnectionState.CLOSED:
                print('Connection closed, retrying')
                try:
                    self._smpp_proto.close()
                except Exception:
                    pass
                self._smpp_proto = None
                self._do_reconnect_future = asyncio.ensure_future(self._do_smpp_reconnect())

            # If proto is not None and is connected, do bind
            elif self._smpp_proto.state == SMPPConnectionState.OPEN:
                if self.config['bind_type'] == 'TX':
                    raise NotImplementedError()
                elif self.config['bind_type'] == 'RX':
                    raise NotImplementedError()
                else:  # TRX
                    self._smpp_proto.bind_trx()

    def connection_lost_trigger(self):
        print('Connection closed, retrying')
        self.close()
        self._do_reconnect_future = asyncio.ensure_future(self._do_smpp_reconnect())


class SMPPManager(object):
    def __init__(self, config: Optional[SMPPConfig]=None, loop: asyncio.AbstractEventLoop=None):
        self.loop = loop
        if not loop:
            self.loop = asyncio.get_event_loop()

        self.config = config

        self.connectors: Dict[str, Tuple[SMPPConnector, asyncio.Future]] = {}

    async def setup(self):
        # Loop through config
        for connector_id, connector_data in self.config.connectors.items():
            if connector_data.get('disabled', '0') == '1':
                print('Skipping {0} (disabled)'.format(connector_id))
            else:
                print('Adding {0}'.format(connector_id))
                await self.add_connector(connector_id, connector_data)

        print('Finished setup')

    async def teardown(self):
        for conn, future in self.connectors.values():
            try:
                conn.close()
                future.cancel()
            except:
                pass

    async def add_connector(self, name: str, data: Dict[str, str]):

        queue_name = 'smpp_' + slugify(name, separator='_')

        smpp_config = {
            'host': data['host'],
            'port': int(data['port']),
            'bind_type': data.get('bind_type', 'TRX'),
            'ssl': data.get('ssl', 'no').lower() == 'yes',
            'systemid': data['systemid'],
            'password': data['password'],
            'conn_loss_retry': data.get('conn_loss_retry', 'yes').lower() == 'yes',
            'conn_loss_delay': int(data.get('conn_loss_delay', '30')),
            'priority_flag': int(data.get('priority', '0')),
            'submit_throughput': int(data.get('submit_throughput', '1')),
            'coding': int(data.get('coding', '1')),
            'enquire_link_interval': int(data.get('enquire_link_interval', '30')),
            'replace_if_present_flag': int(data.get('replace_if_present_flag', '0')),
            'protocol_id': try_format(data.get('proto_id'), int, warn_str='proto_id must be an integer not {0}', allow_none=True),
            'validity_period': try_format(data.get('validity'), int, warn_str='validity must be an integer not {0}', allow_none=True),
            'service_type': data.get('systype'),
            'addr_range': data.get('addr_range'),
            # Type of number / numbering plan identification,
            'source_addr_ton': int(data.get('src_ton', '2')),
            'source_addr_npi': int(data.get('src_npi', '1')),
            'dest_addr_ton': int(data.get('dst_ton', '1')),
            'dest_addr_npi': int(data.get('dst_npi', '1')),
            'bind_ton': int(data.get('bind_ton', '0')),
            'bind_npi': int(data.get('bind_npi', '1')),
            'sm_default_msg_id': int(data.get('sm_default_msg_id', '0')),

            # Non protocol config
            'dlr_msgid': int(data.get('dlr_msgid', '0')),
            'dlr_expiry': int(data.get('dlr_expiry', '86400')),
            'requeue_delay': int(data.get('requeue_delay', '120')),
            'queue_name': queue_name,
            'mq': self.config.mq
        }
        # Value checking
        if smpp_config['bind_type'] not in ('TX', 'RX', 'TRX'):
            print('bind_type ({0}) is not TX, RX, TRX. Setting to TRX'.format(smpp_config['bind_type']))
            smpp_config['bind_type'] = 'TRX'

        conn = SMPPConnector(config=smpp_config)
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

