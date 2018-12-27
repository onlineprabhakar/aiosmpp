import logging

from aiosmpp import log


def test_get_stdout_logger():
    logger_name = 'test1'
    logger_level = logging.WARNING
    logger = log.get_stdout_logger(logger_name, level=logger_level, setup_parent_aiosmpp_logger=True)

    assert logger.name == 'aiosmpp.' + logger_name
    assert logger.level == logger_level
    assert isinstance(logger.parent, logging.Logger)
    assert logger.parent.name == 'aiosmpp'


def test_setup_main_logger():
    logger = log.setup_root_aiosmpp_logger()

    assert logger.name == 'aiosmpp'
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0], logging.StreamHandler)

    log.setup_root_aiosmpp_logger()
    log.setup_root_aiosmpp_logger()
    log.setup_root_aiosmpp_logger()

    # Ensure we dont spam stdout handlers
    assert len(logger.handlers) == 1
