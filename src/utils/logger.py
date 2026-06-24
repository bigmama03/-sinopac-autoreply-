"""Logging configuration."""

import logging
import os
from logging.handlers import RotatingFileHandler

from config import LOG_DIR, APP_NAME


def setup_logger(name: str = APP_NAME) -> logging.Logger:
    """Set up root logger so module-level loggers inherit handlers and level."""
    logger = logging.getLogger()
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler (rotating, 5MB x 5 files)
    log_file = os.path.join(LOG_DIR, "autoreply.log")
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
