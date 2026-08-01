#!/usr/bin/env python3
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import uvicorn

from empire.server.common import empire
from empire.server.core.config import config_manager
from empire.server.core.config.config_manager import (
    CACHE_DIR,
    CONFIG_DIR,
    DATA_DIR,
    empire_config,
)
from empire.server.core.db import base
from empire.server.utils.file_util import run_as_user
from empire.server.utils.log_util import setup_logging

log = logging.getLogger(__name__)


def clean():
    base.reset_db()
    shutil.rmtree(CONFIG_DIR, ignore_errors=True)
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    shutil.rmtree(CACHE_DIR, ignore_errors=True)


def reset():
    base.reset_db()


def shutdown_handler(signum, frame):
    """
    Handle SIGINT during the pre-uvicorn setup phase (cert generation,
    submodule checks, etc.) when MainMenu has not yet been created.

    Once uvicorn is running, it manages SIGINT itself and triggers the
    lifespan's ``finally`` block in app.py, which handles MainMenu shutdown.
    """
    log.info("Shutting down Empire Server...")

    sys.exit(0)


def get_commit_sha() -> str:
    """Return the git commit SHA for the running build.

    In Docker, this is baked in at build time via the EMPIRE_COMMIT_SHA env
    var (set by --build-arg in the Makefile). At runtime (local dev), falls
    back to running git. Returns "unknown" when neither source is available.
    """
    commit = os.environ.get("EMPIRE_COMMIT_SHA", "").strip()
    if commit:
        return commit

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except FileNotFoundError:
        pass

    return "unknown"


def log_version():
    log.info(f"Starting Empire {empire.VERSION} (commit: {get_commit_sha()})")


def check_submodules():
    log.info("Checking submodules...")
    if not Path(".git").exists():
        log.info("No .git directory found. Skipping submodule check.")
        return

    result = subprocess.run(
        ["git", "submodule", "status"], stdout=subprocess.PIPE, text=True, check=False
    )
    for line in result.stdout.splitlines():
        if line[0] == "-":
            log.error(
                "Some git submodules are not initialized. Please run 'git submodule update --init --recursive'"
            )
            sys.exit(1)


def fetch_submodules():
    if not Path(".git").exists():
        log.info("No .git directory found. Skipping submodule fetch.")
        return
    command = ["git", "submodule", "update", "--init", "--recursive"]
    run_as_user(command)


def check_recommended_configuration():
    log.info(f"Using {empire_config.database.use} database.")
    if empire_config.database.use == "sqlite":
        log.warning(
            "Using SQLite may result in performance issues and some functions may be disabled."
        )
        log.warning("Consider using MySQL instead.")


def run(args):
    signal.signal(signal.SIGINT, shutdown_handler)

    if args.version:
        print(empire.VERSION)
        sys.exit()

    setup_logging(args)
    log_version()

    if empire_config.submodules.auto_update:
        log.info("Submodules auto update enabled. Loading.")
        fetch_submodules()
    else:
        log.info("Submodules auto update disabled. Not fetching.")

    check_submodules()
    check_recommended_configuration()

    if args.reset:
        choice = input(
            "\x1b[1;33m[>] Would you like to reset your Empire Server instance? [y/N]: \x1b[0m"
        )
        if choice.lower() == "y":
            reset()

        sys.exit()

    if args.clean:
        choice = input(
            "\x1b[1;33m[>] Would you like to reset your Empire Server instance? [y/N]: \x1b[0m"
        )
        if choice.lower() == "y":
            clean()

        sys.exit()

    else:
        cert_path = config_manager.DATA_DIR / "cert"
        cert_path.mkdir(parents=True, exist_ok=True)
        if not (Path(cert_path) / "empire-chain.pem").exists():
            log.info("Certificate not found. Generating...")
            subprocess.call(["./setup/cert.sh", str(cert_path)])
            time.sleep(3)

        uvicorn_kwargs = {
            "host": empire_config.api.ip,
            "port": empire_config.api.port,
            "log_config": None,
            "lifespan": "on",
        }
        if empire_config.api.secure:
            uvicorn_kwargs["ssl_keyfile"] = f"{cert_path}/empire-priv.key"
            uvicorn_kwargs["ssl_certfile"] = f"{cert_path}/empire-chain.pem"

        uvicorn.run("empire.server.asgi:app", **uvicorn_kwargs)

    sys.exit()
