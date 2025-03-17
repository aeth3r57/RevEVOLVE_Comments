import logging


def start_logging(file_path,name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger_formatter = logging.Formatter('[%(asctime)s][%(name)s][Line %(lineno)d]'
                                         '[%(levelname)s]:%(message)s')

    file_handler = logging.FileHandler(file_path, mode='w')

    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logger_formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logger_formatter)
    stream_handler.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


def stop_logging(logger):
    for handler in logger.handlers:
        handler.close()
