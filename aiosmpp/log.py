import logging


def setup_root_aiosmpp_logger(format_string: str = '[%(asctime)23s - %(name)s - %(levelname)8s]  %(message)s',
                              level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger('aiosmpp')
    logger.setLevel(level)

    if not logger.handlers:
        ch = logging.StreamHandler()
        ch.setLevel(level)

        # create formatter
        formatter = logging.Formatter(format_string)
        formatter.default_msec_format = '%s.%03d'
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    return logger


def get_stdout_logger(name: str, level: int = logging.INFO, setup_parent_aiosmpp_logger: bool = True) -> logging.Logger:
    if setup_parent_aiosmpp_logger:
        setup_root_aiosmpp_logger()

    logger = logging.getLogger('aiosmpp.' + name)
    logger.setLevel(level)

    return logger
