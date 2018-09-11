import logging


def get_stdout_logger(name: str, level: int=logging.INFO) -> logging.Logger:
    logger = logging.getLogger('aiosmpp.' + name)
    logger.setLevel(level)

    ch = logging.StreamHandler()
    ch.setLevel(level)

    # create formatter
    formatter = logging.Formatter('[%(asctime)23s - %(name)s - %(levelname)8s]  %(message)s')
    formatter.default_msec_format = '%s.%03d'
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    logger.propagate = False

    return logger
