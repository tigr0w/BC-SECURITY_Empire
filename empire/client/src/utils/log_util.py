import logging
from pathlib import Path

from empire.server.core.config import empire_config


class MyFormatter(logging.Formatter):
    def format(self, record):
        color = {
            logging.INFO: 34,
            logging.WARNING: 33,
            logging.ERROR: 31,
            logging.FATAL: 31,
            logging.DEBUG: 36,
        }.get(record.levelno, 0)
        self._style._fmt = f"\x1b[1;{color}m%(levelname)s: %(message)s\x1b[0m "
        return super().format(record)


class FileFormatter(logging.Formatter):
    def format(self, record):
        # Check if coloring is applied and remove it
        if "\x1b" in record.msg:
            record.msg = record.msg.replace("\x1b[1;31m", "")
            record.msg = record.msg.replace("\x1b[1;32m", "")
            record.msg = record.msg.replace("\x1b[1;33m", "")
            record.msg = record.msg.replace("\x1b[1;34m", "")
            record.msg = record.msg.replace("\x1b(0l\x1b(B", "")
            record.msg = record.msg.replace("\x1b(0x\x1b(B", "")
            record.msg = record.msg.replace("\x1b[0m", "")
        if "\n" in record.msg:
            record.msg = "\n" + record.msg
        self._style._fmt = (
            "%(asctime)s [%(filename)s:%(lineno)d] [%(levelname)s]: %(message)s "
        )
        return super().format(record)
