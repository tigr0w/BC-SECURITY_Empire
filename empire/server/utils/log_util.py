import logging
from pathlib import Path

from empire.server.common.config import empire_config

LOG_FORMAT = "%(asctime)s [%(filename)s:%(lineno)d] [%(levelname)s]: %(message)s "
SIMPLE_LOG_FORMAT = "[%(levelname)s]: %(message)s "


def get_listener_logger(log_name_prefix: str, listener_name: str):
    log = logging.getLogger(f"{log_name_prefix}.{listener_name}")

    # return if already initialized
    if log.handlers:
        return log

    log.propagate = False

    logging_dir = empire_config.logging.directory
    log_dir = Path(logging_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / f"listener_{listener_name}.log"
    listener_log_file_handler = logging.FileHandler(log_file)
    listener_log_file_handler.setLevel(logging.DEBUG)
    log.addHandler(listener_log_file_handler)
    listener_log_file_handler.setFormatter(logging.Formatter(LOG_FORMAT))

    listener_stream_handler = logging.StreamHandler()
    listener_stream_handler.setLevel(logging.WARNING)
    simple_console = empire_config.logging.simple_console
    if simple_console:
        stream_format = SIMPLE_LOG_FORMAT
    else:
        stream_format = LOG_FORMAT
    listener_stream_handler.setFormatter(ColorFormatter(stream_format))
    log.addHandler(listener_stream_handler)

    return log


class ColorFormatter(logging.Formatter):
    def __init__(self, fmt=None, datefmt=None, style="%", validate=True):
        grey = "\x1b[38;20m"
        blue = "\x1b[34;20m"
        yellow = "\x1b[33;20m"
        red = "\x1b[31;20m"
        bold_red = "\x1b[31;1m"
        reset = "\x1b[0m"

        self.FORMATS = {
            logging.DEBUG: grey + fmt + reset,
            logging.INFO: blue + fmt + reset,
            logging.WARNING: yellow + fmt + reset,
            logging.ERROR: red + fmt + reset,
            logging.CRITICAL: bold_red + fmt + reset,
        }
        super().__init__(fmt, datefmt, style, validate)

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)
