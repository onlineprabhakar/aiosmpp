import re
from typing import List, Union


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


# Routes
class SMPPConnector:
    pass


class Route(object):
    def __init__(self, order: int, data):
        self.order = order
        self.data = data  # Contains connector info

        self.filters: List[TransparentFilter] = []

    def evaluate(self, event: dict) -> bool:
        raise NotImplementedError()

    def _get_connector(self) -> Union[SMPPConnector, None]:
        return None

    @property
    def connector(self) -> Union[SMPPConnector, None]:
        return self._get_connector()


class StaticRoute(Route):
    def __init__(self, order: int, data):
        super(StaticRoute, self).__init__(order, data)

        self._connector = SMPPConnector()

    def evaluate(self, event):
        # Check if we're connected via SMPP
        # if not, this route is useless
        if not self._get_connector():
            return False

        result = True

        for _filter in self.filters:
            try:
                result &= _filter.evaluate(event)
            except Exception as err:
                print(err)
                result = False

            # Short circuit
            if not result:
                break

        return result

    def _get_connector(self):
        # TODO check connector status

        return self._connector


class RouteTable(object):
    def __init__(self):
        self.routes: List[Route] = []

    def _order_routes(self):
        self.routes.sort(reverse=True, key=lambda route: route.order)

    def evaluate(self, event: dict) -> Union[Route, None]:
        for route in self.routes:
            try:
                if route.evaluate(event):
                    return route
            except Exception as err:
                print(err)
        else:
            return None
