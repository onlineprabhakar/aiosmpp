import datetime
from itertools import cycle
from typing import List, Union, Dict, Any

from aiosmpp.interceptor import Interceptor
from aiosmpp.config.smpp import SMPPConfig
from aiosmpp.filters import get_filter, TransparentFilter
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


# Routes
class SMPPConnector:
    def __init__(self, connector_name, config):
        self.name = connector_name
        self.config = config

    @property
    def queue_name(self) -> str:
        return self.config['queue_name']


class Route(object):
    def __init__(self, order: int, connector_name, filters: List[TransparentFilter] = None, config=None):
        self.config = config

        self.order = order
        self.connector_name = connector_name  # Contains connector info

        if not filters:
            filters = []

        self.filters: List[TransparentFilter] = filters

    def evaluate(self, event: dict) -> bool:
        raise NotImplementedError()

    def _get_connector(self) -> Union[SMPPConnector, None]:
        if self.connector_name not in self.config.connectors:
            return None

        # if self.connector_dict['connectors'][self.connector_name]['state'] not in ('BOUND_TRX', 'BOUND_TX'):
        #     return None

        return SMPPConnector(self.connector_name, self.config.connectors[self.connector_name])

    @property
    def connector(self) -> Union[SMPPConnector, None]:
        return self._get_connector()


class StaticRoute(Route):
    def __init__(self, order: int, connector_name, filters=None, config=None):
        super(StaticRoute, self).__init__(order, connector_name, filters, config)

    def evaluate(self, event):
        # Check if we're connected via SMPP
        # if not, this route is useless
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


class SmartRoundRobinRoute(Route):
    def __init__(self, order: int, connectors, filters=None, config=None, status=None):
        self._connectors = connectors.split(',')
        self._connectors_status = status

        self._connector_cycle = cycle(self._connectors)
        self._num_connectors = len(self._connectors)

        super(SmartRoundRobinRoute, self).__init__(order, 'rr', filters, config)

    def evaluate(self, event):
        # Check if we're connected via SMPP
        # if not, this route is useless
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

    def _get_connector(self) -> Union[SMPPConnector, None]:
        count = 0
        while count < self._num_connectors:
            connector_name = next(self._connector_cycle)

            if connector_name not in self.config.connectors:
                count += 1
                continue

            if not self._connectors_status.get(connector_name, '').startswith('BOUND'):
                count += 1
                continue

            return SMPPConnector(connector_name, self.config.connectors[connector_name])
        return None

    def __repr__(self):
        return '<{0: 4d} SmartRoundRobinRoute: {1}>'.format(self.order, ','.join(self._connectors))


class RouteTable(object):
    def __init__(self, config: SMPPConfig):
        self.config = config

    def evaluate(self, event: dict) -> Any:
        raise NotImplementedError()


class MTRouteTable(RouteTable):
    def __init__(self, *args, route_attr='mt_routes', **kwargs):
        super(MTRouteTable, self).__init__(*args, **kwargs)

        self.filters: Dict[str, TransparentFilter] = {}
        self.routes: List[Route] = []
        self._connector_status = {}
        self._last_updated = None

        for filter_name, filter_data in self.config.filters.items():
            self.filters[filter_name] = get_filter(filter_data)

        for route_index, route_data in getattr(self.config, route_attr, []).items():
            route = self._create_route(int(route_index), route_data)
            if route:
                self.routes.append(route)

        self._order_routes()

    def _create_route(self, route_index: int, route_data: Dict[str, Any]) -> Union[Route, None]:
        route_type = route_data.get('type', 'static')

        required_filters = route_data.get('filters', '').split(',')
        if required_filters == ['']:
            required_filters = []

        needed_filters = [self.filters.get(filter_name) for filter_name in required_filters if filter_name]  # noqa: E501
        needed_filters = [x for x in needed_filters if x]

        if len(needed_filters) != len(required_filters):
            # TODO log
            print('Needed {0} filters only got {1}, one of these doesnt exist: {2}'.format(len(required_filters), len(needed_filters),
                                                                                           ', '.join(required_filters)))
            return None

        if route_type in ('static', 'default'):
            return StaticRoute(route_index, route_data['connector'], needed_filters, config=self.config)
        elif route_type == 'smartrr':
            return SmartRoundRobinRoute(route_index, route_data['connectors'], needed_filters, config=self.config, status=self._connector_status)
        else:
            # TODO log
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
                # TODO log
                print(err)
        else:
            return None

    def update_connector_status(self, connector_status_dict: Dict[str, str]):
        self._connector_status.clear()
        self._last_updated = datetime.datetime.utcnow()

        # Should be connector_name => connector_status
        self._connector_status.update(connector_status_dict)


class MTInterceptorTable(RouteTable):
    def __init__(self, *args, **kwargs):
        super(MTInterceptorTable, self).__init__(*args, **kwargs)

        self.filters: Dict[str, TransparentFilter] = {}
        self.interceptors: List[Interceptor] = []

        for filter_name, filter_data in self.config.filters.items():
            self.filters[filter_name] = get_filter(filter_data)

        for interceptor_order, interceptor_data in self.config.mt_interceptors.items():
            filters = []
            for needed_filter in interceptor_data['filters']:
                try:
                    filters.append(self.filters[needed_filter])
                except KeyError:
                    print('Filter {0} not found'.format(needed_filter))

            new_interceptor = Interceptor(interceptor_order, interceptor_data['script'], filters)
            self.interceptors.append(new_interceptor)

    def _order_interceptors(self):
        self.interceptors.sort(reverse=True, key=lambda interceptor: interceptor.order)

    def evaluate(self, event: dict) -> dict:
        for interceptor in self.interceptors:
            if interceptor.match(event):
                return interceptor.run(event)
        return event
