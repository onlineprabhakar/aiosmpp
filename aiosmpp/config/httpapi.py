import configparser
from typing import Callable


class HTTPAPIConfig(object):
    def __init__(self, config: configparser.ConfigParser, reload_func: Callable[[], 'HTTPAPIConfig']):
        self._config = config
        self._reload_func = reload_func

        self.routes = {}
        self.filters = {}

        self._read_config()

    def _read_config(self):
        self.routes.clear()
        self.filters.clear()

        for section in self._config.sections():

            if section.startswith('filter:'):
                self._add_filter(section)
            elif section.startswith('route:'):
                self._add_route(section)
            else:
                print('Unknown section: {0}'.format(section))

    def _add_filter(self, section):
        name = section.split(':', 1)[-1]
        data = dict(self._config[section])

        if name in self.filters:
            print('Filter {0} already exists, overwriting'.format(name))

        self.filters[name] = data

    def _add_route(self, section):
        name = section.split(':', 1)[-1]
        data = dict(self._config[section])

        if name in self.filters:
            print('Route {0} already exists, overwriting'.format(name))

        self.routes[name] = data


    @classmethod
    def from_file(cls, filepath):
        parser = configparser.ConfigParser()
        parser.read(filepath)

        return cls(parser, lambda: cls.from_file(filepath))

    def reload(self):
        new_obj = self._reload_func()
        self._config = new_obj._config
        self._read_config()
