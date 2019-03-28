import asyncio
import datetime
import json
import logging
import sys
from collections import OrderedDict

try:
    from raven.handlers.logging import SentryHandler
except ImportError:
    SentryHandler = None


def setup_root_aiosmpp_logger(format_string: str = '[%(asctime)23s - %(name)s - %(levelname)8s]  %(message)s',
                              level: int = logging.INFO, json_on_nontty: bool = True,
                              configure_task_local_storage: bool = True,
                              sentry_client=None) -> logging.Logger:
    if configure_task_local_storage:
        # Set task factory
        asyncio.get_event_loop().set_task_factory(task_factory)

    logger = logging.getLogger('aiosmpp')
    logger.setLevel(level)

    if not logger.handlers:
        ch = logging.StreamHandler()
        ch.setLevel(level)

        # create formatter
        if sys.stdout.isatty() or not json_on_nontty:
            formatter = logging.Formatter(format_string)
            formatter.default_msec_format = '%s.%03d'
        else:
            formatter = JSONFormatter()

        ch.setFormatter(formatter)
        logger.addHandler(ch)

        if sentry_client and SentryHandler:
            sentry_handler = SentryHandler(client=sentry_client)
            sentry_handler.setLevel(logging.ERROR)
            logger.addHandler(sentry_handler)

    return logger


def get_http_access_logger(name: str, level: int = logging.INFO, setup_parent_aiosmpp_logger: bool = True,
                           json_on_nontty: bool = True, sentry_client=None):
    logger = get_stdout_logger(name, level, setup_parent_aiosmpp_logger)

    logger.propagate = False
    if sys.stdout.isatty() or not json_on_nontty:
        formatter = logging.Formatter()
        formatter.default_msec_format = '%s.%03d'
    else:
        formatter = JSONReqFormatter()

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        if sentry_client and SentryHandler:
            sentry_handler = SentryHandler(client=sentry_client)
            sentry_handler.setLevel(logging.ERROR)
            logger.addHandler(sentry_handler)

    return logger


def get_stdout_logger(name: str, level: int = logging.INFO, setup_parent_aiosmpp_logger: bool = True,
                      sentry_client=None) -> logging.Logger:
    if setup_parent_aiosmpp_logger:
        setup_root_aiosmpp_logger(sentry_client=sentry_client)

    logger = logging.getLogger('aiosmpp.' + name)
    logger.setLevel(level)

    return logger


class JSONFormatter(logging.Formatter):
    @staticmethod
    def format_timestamp(time):
        return datetime.datetime.utcfromtimestamp(time).isoformat() + 'Z'

    def format(self, record, serialize=True):
        try:
            msg = record.msg % record.args
        except TypeError:
            msg = record.msg

        # Deal with tracebacks
        exc = ''
        if record.exc_info:
            # Cache the traceback text to avoid converting it multiple times
            # (it's constant anyway)
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            if exc[-1:] != '\n':
                exc += '\n'
            exc += record.exc_text
        if record.stack_info:
            if exc[-1:] != '\n':
                exc += '\n'
            exc += self.formatStack(record.stack_info)
        exc = exc.strip('\n')

        message = OrderedDict((
            ('timestamp', self.format_timestamp(record.created)),
            ('level', record.levelname),
            ('message', msg),
            ('logger', record.name),
            ('filename', record.filename),
            ('lineno', record.lineno)
        ))

        if len(exc) > 0:
            message['traceback'] = exc
        if hasattr(record, 'data'):
            message['data'] = record.data

        try:
            current_task = asyncio.Task.current_task()
            if current_task and hasattr(current_task, 'context'):
                message['req_id'] = current_task.context.get('req_id', 'unknown')
        except Exception:
            pass

        try:
            return json.dumps(message)
        except Exception as err:
            msg = {
                'timestamp': message['timestamp'],
                'level': 'ERROR',
                'message': 'Error whilst json logging',
                'logger': record.name,
                'traceback': self.formatException(err)
            }
            return json.dumps(msg)


def task_factory(loop, coro) -> asyncio.Task:
    """
    Task factory function
    Fuction closely mirrors the logic inside of
    asyncio.BaseEventLoop.create_task. Then if there is a current
    task and the current task has a context then share that context
    with the new task
    """
    task = asyncio.Task(coro, loop=loop)
    if task._source_traceback:  # flake8: noqa
        del task._source_traceback[-1]  # flake8: noqa

    # Share context with new task if possible
    current_task = asyncio.Task.current_task(loop=loop)
    if current_task is not None and hasattr(current_task, 'context'):
        setattr(task, 'context', current_task.context)

    return task


class JSONReqFormatter(JSONFormatter):
    def format(self, record, serialize=True):
        # Create message dict
        if 'X-Forwarded-For' in record.request.headers:
            remote = record.request.headers['X-Forwarded-For']
        else:
            remote = record.request.remote

        message = OrderedDict((
            ('timestamp', self.format_timestamp(record.created)),
            ('logger', record.name),
            ('level', record.levelname),
            ('method', record.request.method),
            ('path', record.request.path_qs),
            ('remote', remote),
            ('user_agent', record.request.headers['user-agent']),
            ('host', record.request.host),
            ('response_time', round(record.time, 2)),
            ('req_id', record.request.get('req_id', 'unknown'))
        ))

        if record.response is not None:  # not Websocket
            message['status_code'] = record.response.status
            if hasattr(record.response, 'body'):
                message['length'] = record.response.headers.get('content-length', -1)
            else:
                message['length'] = -1

            message['type'] = 'access'
        else:
            message['type'] = 'ws_access'

        # Can't remember why I added this
        if 'error_message' in record.request:
            try:
                message['request_info']['error_message'] = record.request['error_message']
            except KeyError:
                message['request_info'] = {'error_message': record.request['error_message']}

        return json.dumps(message)
