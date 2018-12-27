import re
from typing import List, Union, Dict, Any


# Event
# {
#    "pdus": [{ PDU }, ...],
#    "to": "447400000001",
#    "from": "447500000002",
#    "timestamp": 1534782956.063949,
#    "msg": "hello world",
#    "direction": "MT",
#    "tags": [1,5,70]
# # MO ------
#    "origin-connector": "clx_us_trx"
# # MT ------
#    "dlr": {
#        "url": "http://example.org/dlr.php",
#        "level": 3,
#        "method": "POST"
#    }
# }
#


class TransparentFilter(object):
    def evaluate(self, event: dict) -> bool:
        return True


class ConnectorFilter(TransparentFilter):
    def __init__(self, connector: str):
        self.connector = connector

    def evaluate(self, event):
        return event.get('origin-connector', '__unknown__') == self.connector


class SourceAddrFilter(TransparentFilter):
    FIELD = 'to'

    def __init__(self, filter_regex: str):
        self.regex = re.compile(filter_regex)

    def evaluate(self, event):
        val = event.get(self.FIELD, '__unknown__')
        return self.regex.match(val) is not None


class DestinationAddrFilter(SourceAddrFilter):
    FIELD = 'from'


class ShortMessageFilter(SourceAddrFilter):
    FIELD = 'msg'


class TagFilter(TransparentFilter):
    def __init__(self, tag: int):
        self.tag = tag

    def evaluate(self, event):
        return self.tag in event.get('tags', [])


def get_filter(filter_data):
    filter_type = filter_data.get('type', 'transparent')

    if filter_type == 'tag':
        return TagFilter(int(filter_data['tag']))
    elif filter_type == 'destaddr':
        return DestinationAddrFilter(filter_data['regex'])
    else:
        return TransparentFilter()


# Routes
class SMPPConnector:
    def __init__(self, connector_name, connector_data):
        self.name = connector_name
        self.state = connector_data['state']
        self.config = connector_data['config']

    @property
    def queue_name(self) -> str:
        return self.config['queue_name']

    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'data': {
                'state': self.state,
                'config': self.config
            }
        }

    @classmethod
    def from_dict(cls, data_dict: dict):
        return cls(data_dict['name'], data_dict['data'])


class Route(object):
    def __init__(self, order: int, connector_name, filters: List[TransparentFilter] = None, connector_dict=None):
        if connector_dict is None:
            connector_dict = {'connectors': {}}

        self.order = order
        self.connector_name = connector_name  # Contains connector info
        self.connector_dict = connector_dict

        if not filters:
            filters = []

        self.filters: List[TransparentFilter] = filters

    def evaluate(self, event: dict) -> bool:
        raise NotImplementedError()

    def _get_connector(self) -> Union[SMPPConnector, None]:
        if self.connector_name not in self.connector_dict['connectors']:
            return None

        if self.connector_dict['connectors'][self.connector_name]['state'] not in ('BOUND_TRX', 'BOUND_TX'):
            return None

        return SMPPConnector(self.connector_name, self.connector_dict['connectors'][self.connector_name])

    @property
    def connector(self) -> Union[SMPPConnector, None]:
        return self._get_connector()


class StaticRoute(Route):
    def __init__(self, order: int, connector_name, filters=None, connector_dict=None):
        super(StaticRoute, self).__init__(order, connector_name, filters, connector_dict)

    def evaluate(self, event):
        # Check if we're connected via SMPP
        # if not, this route is useless
        if not self.connector:
            return False

        result = True

        for _filter in self.filters:
            try:
                result &= _filter.evaluate(event)
            except Exception as err:
                # TODO log
                print(err)
                result = False

            # Short circuit
            if not result:
                break

        return result

    def __repr__(self):
        return '<{0: 4d} StaticRoute: {1}>'.format(self.order, self.connector_name)


class RouteTable(object):
    def __init__(self, config, route_attr='mt_routes', connector_dict=None):
        if connector_dict is None:
            connector_dict = {}

        self.connector_dict = connector_dict

        self.filters: Dict[str, TransparentFilter] = {}
        self.routes: List[Route] = []

        for filter_name, filter_data in config.filters.items():
            self.filters[filter_name] = get_filter(filter_data)

        for route_index, route_data in getattr(config, route_attr, []).items():
            route = self._create_route(int(route_index), route_data)
            if route:
                self.routes.append(route)

        self._order_routes()

    def _create_route(self, route_index: int, route_data: Dict[str, Any]) -> Union[Route, None]:
        route_type = route_data.get('type', 'static')

        needed_filters = [self.filters.get(filter_name) for filter_name in route_data.get('filters', '').split(',') if filter_name]
        needed_filters = [x for x in needed_filters if x]

        if route_type in ('static', 'default'):
            return StaticRoute(route_index, route_data['connector'], needed_filters, connector_dict=self.connector_dict)
        else:
            print('Unknown route type {0}'.format(route_type))

        return None

    def _order_routes(self):
        self.routes.sort(reverse=True, key=lambda route: route.order)

    def evaluate(self, event: dict) -> Union[SMPPConnector, None]:
        for route in self.routes:
            try:
                if route.evaluate(event):
                    return route.connector
            except Exception as err:
                print(err)
        else:
            return None
