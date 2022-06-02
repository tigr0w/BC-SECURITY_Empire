#!/usr/bin/env python3
import logging
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import urllib3

# Empire imports
from empire.server.common import empire
from empire.server.common.config import empire_config
from empire.server.database import base
from empire.server.utils import file_util
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


CSHARP_DIR_BASE = os.path.join(os.path.dirname(__file__), "csharp/Covenant")
INVOKE_OBFS_SRC_DIR_BASE = os.path.join(
    os.path.dirname(__file__), "powershell/Invoke-Obfuscation"
)
INVOKE_OBFS_DST_DIR_BASE = "/usr/local/share/powershell/Modules/Invoke-Obfuscation"


def reset():
    base.reset_db()

    file_util.remove_dir_contents(empire_config.directories.downloads)

    if os.path.exists(f"{CSHARP_DIR_BASE}/bin"):
        shutil.rmtree(f"{CSHARP_DIR_BASE}/bin")

    if os.path.exists(f"{CSHARP_DIR_BASE}/obj"):
        shutil.rmtree(f"{CSHARP_DIR_BASE}/obj")

    file_util.remove_dir_contents(f"{CSHARP_DIR_BASE}/Data/Tasks/CSharp/Compiled/net35")
    file_util.remove_dir_contents(f"{CSHARP_DIR_BASE}/Data/Tasks/CSharp/Compiled/net40")
    file_util.remove_dir_contents(
        f"{CSHARP_DIR_BASE}/Data/Tasks/CSharp/Compiled/netcoreapp3.0"
    )

    # invoke obfuscation
    if os.path.exists(f"{INVOKE_OBFS_DST_DIR_BASE}"):
        shutil.rmtree(INVOKE_OBFS_DST_DIR_BASE)
    pathlib.Path(pathlib.Path(INVOKE_OBFS_SRC_DIR_BASE).parent).mkdir(
        parents=True, exist_ok=True
    )
    shutil.copytree(
        INVOKE_OBFS_SRC_DIR_BASE, INVOKE_OBFS_DST_DIR_BASE, dirs_exist_ok=True
    )


def shutdown_handler(signum, frame):
    """
    This is used to gracefully shutdown Empire if uvicorn is not running yet.
    Otherwise, the "shutdown" event in v2App.py will be used.
    """
    log.info("Shutting down Empire Server...")

    if main:
        log.info("Shutting down MainMenu...")
        main.shutdown()

    exit(0)


signal.signal(signal.SIGINT, shutdown_handler)


def run(args):
    setup_logging(args)

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
        choice = input(
            "\x1b[1;33m[>] Would you like to reset your Empire Server instance? [y/N]: \x1b[0m"
        )
        if choice.lower() == "y":
            reset()

        sys.exit()

    else:
        global main

        # Calling run more than once, such as in the test suite
        # Will generate more instances of MainMenu, which then
        # causes shutdown failure.
        if main is None:
            main = empire.MainMenu(args=args)

        if not os.path.exists("./empire/server/data/empire-chain.pem"):
            log.info("Certificate not found. Generating...")
            subprocess.call("./setup/cert.sh")
            time.sleep(3)

        v2App.initialize()

    sys.exit()
