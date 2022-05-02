#!/usr/bin/env python3
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

import urllib3

# Empire imports
from empire.server.common import empire
from empire.server.common.config import empire_config
from empire.server.utils.log_util import LOG_FORMAT, SIMPLE_LOG_FORMAT, ColorFormatter
from empire.server.v2.api import v2App

log = logging.getLogger(__name__)
main = None


# Disable http warnings
if empire_config.supress_self_cert_warning:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def setup_logging(args):
    if args.log_level:
        log_level = logging.getLevelName(args.log_level.upper())
    else:
        log_level = logging.getLevelName(empire_config.logging.level.upper())

    logging_dir = empire_config.logging.directory
    log_dir = Path(logging_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    root_log_file = log_dir / "empire_server.log"
    root_logger = logging.getLogger()
    # If this isn't set to DEBUG, then we won't see debug messages from the listeners.
    root_logger.setLevel(logging.DEBUG)

    root_logger_file_handler = logging.FileHandler(root_log_file)
    root_logger_file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root_logger.addHandler(root_logger_file_handler)

    simple_console = empire_config.logging.simple_console
    if simple_console:
        stream_format = SIMPLE_LOG_FORMAT
    else:
        stream_format = LOG_FORMAT
    root_logger_stream_handler = logging.StreamHandler()
    root_logger_stream_handler.setFormatter(ColorFormatter(stream_format))
    root_logger_stream_handler.setLevel(log_level)
    root_logger.addHandler(root_logger_stream_handler)


def run(args):
    setup_logging(args)
    global main
    main = empire.MainMenu(args=args)
    if not args.restport:
        args.restport = "1337"
    else:
        args.restport = args.restport[0]

    if not args.restip:
        args.restip = "0.0.0.0"
    else:
        args.restip = args.restip[0]

    if args.version:
        log.info(empire.VERSION)
        sys.exit()

    elif args.reset:
        # todo vr Reset called from database/base.py
        sys.exit()

    else:
        if not os.path.exists("./empire/server/data/empire-chain.pem"):
            log.info("Certificate not found. Generating...")
            subprocess.call("./setup/cert.sh")
            time.sleep(3)

        v2App.initialize()

    sys.exit()
