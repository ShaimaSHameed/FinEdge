import logging
import sys
from typing import Any

_loggers = {}


def get_logger(name: str) -> logging.Logger:
    if name not in _loggers:
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)

        if not logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        _loggers[name] = logger

    return _loggers[name]
