import argparse
import asyncio
import os
import sys
from typing import Optional, Dict

from aiosmpp.config.smpp import SMPPConfig
from aiosmpp.client import SMPPClientProtocol


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


class SMPPManager(object):
    def __init__(self, config: Optional[SMPPConfig]=None, loop: asyncio.AbstractEventLoop=None):
        self.loop = loop
        if not loop:
            self.loop = asyncio.get_event_loop()

        self.config = config

        self.connectors = {}

    async def setup(self):
        # Loop through config
        for connector_id, connector_data in self.config.connectors.items():
            if connector_data.get('disabled', '0') == '1':
                print('Skipping {0} (disabled)'.format(connector_id))
            else:
                print('Adding {0}'.format(connector_id))
                await self.add_connector(connector_id, connector_data)

        print('Finished setup')

    async def add_connector(self, name: str, data: Dict[str, str]):
        smpp_data = {
            'host': data['host'],
            'port': int(data['port']),
            'bind_type': data.get('bind_type', 'TRX'),
            'ssl': data.get('ssl', 'no').lower() == 'yes',
            'systemid': data['systemid'],
            'password': data['password'],
            'conn_loss_retry': data.get('conn_loss_retry', 'yes').lower() == 'yes',
            'conn_loss_delay': int(data.get('src_ton', '30')),
            'priority': int(data.get('priority', '0')),
            'requeue_delay': int(data.get('requeue_delay', '120')),
            'dlr_expiry': int(data.get('dlr_expiry', '86400')),
            'submit_throughput': int(data.get('submit_throughput', '1')),
            'coding': int(data.get('coding', '1')),
            'enquire_link_interval': int(data.get('enquire_link_interval', '30')),
            'replace_if_present_flag': int(data.get('replace_if_present_flag', '0')),
            'dlr_msgid': int(data.get('dlr_msgid', '0')),
            'proto_id': try_format(data.get('proto_id'), int, warn_str='proto_id must be an integer not {0}', allow_none=True),
            'validity': try_format(data.get('validity'), int, warn_str='validity must be an integer not {0}', allow_none=True),
            'systype': data.get('systype'),
            'addr_range': data.get('addr_range'),
            # Type of number / numbering plan identification,
            'src_ton': int(data.get('src_ton', '2')),
            'src_npi': int(data.get('src_npi', '1')),
            'dst_ton': int(data.get('dst_ton', '1')),
            'dst_npi': int(data.get('dst_npi', '1')),
            'bind_ton': int(data.get('bind_ton', '0')),
            'bind_npi': int(data.get('bind_npi', '1')),
        }

        conn = await self.loop.create_connection(lambda: SMPPClientProtocol(config=smpp_data, loop=self.loop), smpp_data['host'], smpp_data['port'])
        self.connectors[name] = conn

        # TODO run bind
        # TODO hook up connection lost trigger
        # TODO hook up state change trigger
        # TODO re-bind after delay

        # TODO generate queue name
        # TODO create queue for connection

        pass


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


    await asyncio.sleep(20)

if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(main())

