import configparser
import logging
from typing import Callable, Optional


class HTTPAPIConfig(object):
    def __init__(self, config: configparser.ConfigParser, reload_func: Callable[[], 'HTTPAPIConfig'],
                 logger: Optional[logging.Logger] = None):
        self.logger = logger
        if not logger:
            self.logger = logging.getLogger()

        self._config = config
        self._reload_func = reload_func

        self.mt_routes = {}
        self.mo_routes = {}
        self.filters = {}

        self.mq = {}

        self._read_config()

    def _read_config(self):
        self.mt_routes.clear()
        self.mo_routes.clear()
        self.filters.clear()

        self.mq = {
            'host': self._config.get('mq', 'host', fallback='127.0.0.1'),
            'port': self._config.getint('mq', 'port', fallback=5672),
            'vhost': self._config.get('mq', 'vhost', fallback='/'),
            'user': self._config.get('mq', 'user', fallback='guest'),
            'password': self._config.get('mq', 'password', fallback='guest'),
            'heartbeat_interval': self._config.getint('mq', 'heartbeat', fallback=30),
            'ssl': self._config.getboolean('mq', 'ssl', fallback=False)
        }

        for section in self._config.sections():
            if section.startswith('mo_route:') or section.startswith('smpp_bind:'):
                continue
            elif section.startswith('filter:'):
                self._add_filter(section)
            elif section.startswith('mt_route:'):
                self._add_mt_route(section)
            else:
                self.logger.warning('Unknown section: {0}'.format(section))

    def _add_filter(self, section):
        name = section.split(':', 1)[-1]
        data = dict(self._config[section])

        if name in self.filters:
            self.logger.warning('Filter {0} already exists, overwriting'.format(name))

        self.filters[name] = data

    def _add_mt_route(self, section):
        name, data = self._add_route(section)

        self.mt_routes[name] = data

    def _add_route(self, section):
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
            reload_func = lambda: cls.from_file(filepath)  # noqa: E731
        elif config:
            parser.read_string(config)
            reload_func = lambda: cls.from_file(config=config)  # noqa: E731
        else:
            raise ValueError('filepath or config argument must be provided')

        return cls(parser, reload_func, logger=logger)

    def reload(self):
        new_obj = self._reload_func()
        self._config = new_obj._config
        self._read_config()
