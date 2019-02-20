import configparser
import logging
import os
import string
from typing import Callable, Optional, Tuple, Dict, Any

from aiosmpp import constants as c


def _try_format(value: Any, func, default: Any = None, warn_str: str = None, allow_none: bool = False, logger: logging.Logger = None):
    if allow_none and value is None:
        return value

    try:
        value = func(value)
    except Exception:
        if warn_str and logger:
            logger.warning(warn_str.format(value=value))
        value = default
    return value


class SMPPConfig(object):
    SQS_VALID = string.ascii_letters + string.digits + '-_'

    def __init__(self, config: configparser.ConfigParser, reload_func: Callable[[], 'SMPPConfig'],
                 logger: Optional[logging.Logger] = None):
        self.logger = logger
        if not logger:
            self.logger = logging.getLogger('aiosmpp.config')

        self._config = config
        self._reload_func = reload_func

        self.connectors = {}
        self.filters = {}
        self.mt_routes = {}
        self.mo_routes = {}

        self.mt_interceptors = {}

        self.mq = {}
        self.redis = {}

        self.dlr_queue = None
        self.mo_queue = None
        self.smpp_client_url = None

        self._read_config()

    @classmethod
    def sqs_queue_filter(cls, name: str) -> str:
        """
        Crude string to SQS queue name formatter
        """
        return ''.join([char if char in cls.SQS_VALID else '' if char == ' ' else '-' for char in name])

    def _read_config(self):
        self.connectors.clear()
        self.mt_routes.clear()
        self.mo_routes.clear()
        self.mt_interceptors.clear()
        self.filters.clear()

        # Get MQ settings
        self.mq = {
            'region': self._config.get('sqs', 'region'),
            'aws_endpoint': self._config.get('sqs', 'endpoint', fallback=None),
            'name_prefix': self._config.get('sqs', 'prefix', fallback=''),
            'use_fifo_for_sms_queues': self._config.getboolean('sqs', 'use_fifo_for_sms_queues', fallback=False),
            'use_fifo_for_dlr': self._config.getboolean('sqs', 'use_fifo_for_dlr', fallback=False),
            'use_fifo_for_mo': self._config.getboolean('sqs', 'use_fifo_for_mo', fallback=False)
        }
        if self.mq['name_prefix']:
            self.mq['name_prefix'] += '_'
        self.mq['name_suffix'] = '.fifo' if self.mq['use_fifo_for_sms_queues'] else ''

        self.dlr_queue = self.mq['name_prefix'] + c.DLR_QUEUE + ('.fifo' if self.mq['use_fifo_for_dlr'] else '')
        self.mo_queue = self.mq['name_prefix'] + c.MO_QUEUE + ('.fifo' if self.mq['use_fifo_for_mo'] else '')

        self.smpp_client_url = self._config.get('smpp_client', 'url')

        for section in self._config.sections():

            if section in ('sqs',):
                continue
            elif section.startswith('mo_route:'):
                self._add_mo_route(section)
            elif section.startswith('smpp_bind:'):
                self._add_connector(section)
            elif section.startswith('filter:'):
                self._add_filter(section)
            elif section.startswith('mt_route:'):
                self._add_mt_route(section)
            elif section.startswith('mt_interceptor:'):
                self._add_mt_interceptor(section)
            else:
                self.logger.warning('Unknown section: {0}'.format(section))

        # Get Redis settings
        self.redis = {
            'host': self._config.get('redis', 'host', fallback='127.0.0.1'),
            'port': self._config.getint('redis', 'port', fallback=6379),
            'db': self._config.getint('redis', 'db', fallback=0),
        }

    def _add_connector(self, section: str):
        name = section.split(':', 1)[-1]
        data = dict(self._config[section])

        if name in self.connectors:
            self.logger.warning('Connector {0} already exists, overwriting'.format(name))

        queue_name = self.mq['name_prefix'] + self.sqs_queue_filter('smppconn_' + name) + self.mq['name_suffix']

        # Convert whats in the config to all the SMPP settings
        final = {
            'connector_name': name,
            'logger_name': queue_name.replace('.', '_'),
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
            'protocol_id': _try_format(data.get('proto_id'), int, warn_str='proto_id must be an integer not {0}', allow_none=True, logger=self.logger),
            'validity_period': _try_format(data.get('validity'), int, warn_str='validity must be an integer not {0}', allow_none=True, logger=self.logger),
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
            'dlr_queue_name': self.dlr_queue,
            'mo_queue_name': self.mo_queue,
            'mq': self.mq
        }

        self.connectors[name] = final

    def _add_filter(self, section: str):
        name = section.split(':', 1)[-1]
        data = dict(self._config[section])

        if name in self.filters:
            self.logger.warning('Filter {0} already exists, overwriting'.format(name))

        self.filters[name] = data

    def _add_mo_route(self, section: str):
        name, data = self._get_route(section)

        self.mo_routes[name] = data

    def _add_mt_route(self, section: str):
        name, data = self._get_route(section)

        self.mt_routes[name] = data

    def _add_mt_interceptor(self, section: str):
        name = section.split(':', 1)[-1]
        script = self._config.get(section, 'script', fallback=None)
        filters = self._config.get(section, 'filters', fallback=None)
        if filters is None:
            filters = []
        else:
            filters = [item.strip() for item in filters.split(',')]

        if script:
            script = os.path.abspath(script)
            self.mt_interceptors[name] = {'script': script, 'filters': filters}

    def _get_route(self, section: str) -> Tuple[str, Dict[str, Any]]:
        name = section.split(':', 1)[-1]
        data = dict(self._config[section])

        if name in self.filters:
            self.logger.warning('Route {0} already exists, overwriting'.format(name))

        return name, data

    @classmethod
    def from_file(cls, filepath: str = None, config: str = None, logger: Optional[logging.Logger] = None):
        parser = configparser.ConfigParser()
        if filepath:
            parser.read(filepath)
            reload_func = lambda: cls.from_file(filepath)
        elif config:
            parser.read_string(config)
            reload_func = lambda: cls.from_file(config=filepath)
        else:
            raise ValueError('filepath or config argument must be provided')

        return cls(parser, reload_func, logger=logger)

    def reload(self):
        new_obj = self._reload_func()
        self._config = new_obj._config
        self._read_config()
