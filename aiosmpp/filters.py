import re


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


def get_filter(filter_data) -> TransparentFilter:
    filter_type = filter_data.get('type', 'transparent')

    if filter_type == 'tag':
        return TagFilter(int(filter_data['tag']))
    elif filter_type == 'destaddr':
        return DestinationAddrFilter(filter_data['regex'])
    else:
        return TransparentFilter()
