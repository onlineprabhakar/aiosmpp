import os
import logging
import importlib.util
from typing import List, Optional, Callable

from aiosmpp.log import get_stdout_logger
from aiosmpp.filters import TransparentFilter


class Interceptor(object):
    def __init__(self, order: str, script: str, filters: Optional[List[TransparentFilter]] = None, logger: logging.Logger = None):
        if filters is None:
            filters = []
        if logger is None:
            logger = get_stdout_logger('mt_intercept.' + os.path.basename(script.replace('.py', '')))

        self.order = order
        self.script = script
        self.filters = filters
        self.logger = logger

        self._import: Callable[[dict, logging.Logger], dict] = None
        if not os.path.exists(script):
            self.logger.warning('Interceptor {0} doesn\'t exist, will ignore'.format(script))
        else:
            try:
                spec = importlib.util.spec_from_file_location('mt_interceptor_' + order, script)
                imported_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(imported_module)

                if hasattr(imported_module, 'process'):
                    self._import = imported_module.process
                else:
                    self.logger.warning('MT intercept module {0} does not have valid process function')

            except Exception as err:
                self.logger.exception('Failed to load MT intercept module {0}'.format(script), exc_info=err)

    def match(self, event: dict) -> bool:
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

    def run(self, event: dict) -> dict:
        result = event

        if self._import is None:
            self.logger.warning('Skipping interceptor as its not configured')
            return result

        try:
            new_result = self._import(event.copy(), self.logger)

            # Spot checks that the event is still legit, we should look into this more
            if not isinstance(new_result, dict):
                self.logger.error('MT Interceptor result is not a dict')
            elif 'pdus' not in new_result:
                self.logger.error('MT Interceptor result does not contain pdus')
            else:
                # All good, should check some more though
                result = new_result

        except Exception as err:
            self.logger.exception('Caught exception whilst trying to process interceptor', exc_info=err)

        return result


def lock_pdu_param(event: dict, param: str):
    if param not in event['locked']:
        event['locked'].append(param)
