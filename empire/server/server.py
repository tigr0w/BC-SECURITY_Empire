#!/usr/bin/env python3
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

import urllib3
from flask import jsonify, make_response, request

# Empire imports
from empire.server.common import empire
from empire.server.common.config import empire_config
from empire.server.utils.log_util import LOG_FORMAT, SIMPLE_LOG_FORMAT, ColorFormatter
from empire.server.v2.api import v2App

log = logging.getLogger(__name__)


# Disable http warnings
if empire_config.yaml.get("suppress-self-cert-warning", True):
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def setup_logging(args):
    if args.log_level:
        log_level = logging.getLevelName(args.log_level.upper())
    else:
        log_level = logging.getLevelName(
            empire_config.yaml.get("logging", {}).get("level", "INFO").upper()
        )

    logging_dir = empire_config.yaml.get("logging", {}).get(
        "directory", "empire/server/downloads/logs/"
    )
    log_dir = Path(logging_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    root_log_file = log_dir / "empire_server.log"
    root_logger = logging.getLogger()
    # If this isn't set to DEBUG, then we won't see debug messages from the listeners.
    root_logger.setLevel(logging.DEBUG)

    root_logger_file_handler = logging.FileHandler(root_log_file)
    root_logger_file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root_logger.addHandler(root_logger_file_handler)

    simple_console = empire_config.yaml.get("logging", {}).get("simple_console", True)
    if simple_console:
        stream_format = SIMPLE_LOG_FORMAT
    else:
        stream_format = LOG_FORMAT
    root_logger_stream_handler = logging.StreamHandler()
    root_logger_stream_handler.setFormatter(ColorFormatter(stream_format))
    root_logger_stream_handler.setLevel(log_level)
    root_logger.addHandler(root_logger_stream_handler)


def start_restful_api():
    # todo vr: can we remove the global obfuscate flag and if not, how should it be handled in v2?
    def set_admin_options():
        """
        Admin menu options for obfuscation
        """
        # Set global obfuscation
        if "obfuscate" in request.json:
            if request.json["obfuscate"].lower() == "true":
                main.obfuscate = True
            else:
                main.obfuscate = False
            msg = f"[*] Global obfuscation set to {request.json['obfuscate']}"

        # if obfuscate command is given then set, otherwise use default
        elif "obfuscate_command" in request.json:
            main.obfuscateCommand = request.json["obfuscate_command"]
            msg = f"[*] Global obfuscation command set to {request.json['obfuscate_command']}"

        elif "preobfuscation" in request.json:
            obfuscate_command = request.json["preobfuscation"]
            if request.json["force_reobfuscation"].lower() == "true":
                force_reobfuscation = True
            else:
                force_reobfuscation = False
            msg = f"[*] Preobfuscating all modules with {obfuscate_command}"
            main.preobfuscate_modules(obfuscate_command, force_reobfuscation)
        else:
            return make_response(
                jsonify({"error": "JSON body must include key valid admin option"}), 400
            )
        return jsonify({"success": True})


main = None


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
        # todo vr this isn't exiting properly.
        log.info(empire.VERSION)

    elif args.reset:
        # Reset called from database/base.py
        sys.exit()

    else:
        if not os.path.exists("./empire/server/data/empire-chain.pem"):
            log.info("Certificate not found. Generating...")
            subprocess.call("./setup/cert.sh")
            time.sleep(3)

        def thread_v2_api():
            v2App.initialize()

        thread_v2_api()

        # thread3 = helpers.KThread(target=thread_v2_api)
        # thread3.daemon = True
        # thread3.start()
        # sleep(2)

        # main.teamserver()

    sys.exit()
