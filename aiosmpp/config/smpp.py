import configparser
from typing import Callable


class SMPPConfig(object):
    def __init__(self, config: configparser.ConfigParser, reload_func: Callable[[], 'SMPPConfig']):
        self._config = config
        self._reload_func = reload_func

        self.connectors = {}

        self.mq = {}
        self.redis = {}

        self._read_config()

    def _read_config(self):
        self.connectors.clear()

        for section in self._config.sections():

            if section.startswith('mt_route:') or section.startswith('mo_route:') or \
                    section.startswith('filter:') or section in ('mq',):
                continue
            elif section.startswith('smpp_bind:'):
                self._add_connector(section)
            else:
                print('Unknown section: {0}'.format(section))

        # Get MQ settings
        self.mq = {
            'host': self._config.get('mq', 'host', fallback='127.0.0.1'),
            'port': self._config.getint('mq', 'port', fallback=5672),
            'vhost': self._config.get('mq', 'vhost', fallback='/'),
            'user': self._config.get('mq', 'user', fallback='guest'),
            'password': self._config.get('mq', 'password', fallback='guest'),
            'heartbeat_interval': self._config.getint('mq', 'heartbeat', fallback=30)
        }

        # Get Redis settings
        self.redis = {
            'host': self._config.get('redis', 'host', fallback='127.0.0.1'),
            'port': self._config.getint('redis', 'port', fallback=6379),
            'db': self._config.getint('redis', 'db', fallback=0),
        }

    def _add_connector(self, section):
        name = section.split(':', 1)[-1]
        data = dict(self._config[section])

        if name in self.connectors:
            print('Connector {0} already exists, overwriting'.format(name))

        self.connectors[name] = data

    @classmethod
    def from_file(cls, filepath: str = None, config: str = None):
        parser = configparser.ConfigParser()
        if filepath:
            parser.read(filepath)
            reload_func = lambda: cls.from_file(filepath)
        elif config:
            parser.read_string(config)
            reload_func = lambda: cls.from_file(config=filepath)
        else:
            raise ValueError('filepath or config argument must be provided')

        return cls(parser, reload_func)

    def reload(self):
        new_obj = self._reload_func()
        self._config = new_obj._config
        self._read_config()
