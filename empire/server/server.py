#!/usr/bin/env python3
import logging
import os
import shutil
import signal
import subprocess
import sys

import uvicorn

from empire.server.common import empire
from empire.server.core.config import config_manager, paths
from empire.server.core.config.config_manager import (
    CACHE_DIR,
    CONFIG_DIR,
    DATA_DIR,
    empire_config,
)
from empire.server.core.db import base
from empire.server.utils import cert_util
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
    Handle SIGINT during the pre-uvicorn setup phase (cert generation, etc.)
    when MainMenu has not yet been created.

    Once uvicorn is running, it manages SIGINT itself and triggers the
    lifespan's ``finally`` block in app.py, which handles MainMenu shutdown.
    """
    log.info("Shutting down Empire Server...")

    sys.exit(0)


def get_commit_sha() -> str:
    """Return the git commit SHA for the running build.

    In Docker, this is baked in at build time via the EMPIRE_COMMIT_SHA env
    var (set by --build-arg in the Makefile). From a git checkout, falls back
    to running git against the repository root -- never the CWD, which on a
    package install would report a neighbouring repository's HEAD as Empire's
    own. Returns "unknown" when neither source is available.
    """
    commit = os.environ.get("EMPIRE_COMMIT_SHA", "").strip()
    if commit:
        return commit

    if not paths.is_git_checkout():
        return "unknown"

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=paths.REPO_ROOT,
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
        # generate_self_signed_cert creates the directory itself.
        cert_path = config_manager.CERT_DIR
        # Both halves, not just the certificate: the two files are written
        # separately, so an interrupted run can leave one of them behind on
        # its own. Gating on the certificate alone would skip regeneration
        # forever after a run that wrote only the key, and the mismatch only
        # ever surfaces as an "[SSL] key values mismatch" line from inside a
        # listener's startup handler.
        if not (
            (cert_path / cert_util.CERT_FILENAME).exists()
            and (cert_path / cert_util.KEY_FILENAME).exists()
        ):
            log.info("Certificate or private key not found. Generating...")
            cert_file, key_file = cert_util.generate_self_signed_cert(cert_path)
            log.info(f"Certificate written to {cert_file}")
            log.info(f"Private key written to {key_file}")

        uvicorn_kwargs = {
            "host": empire_config.api.ip,
            "port": empire_config.api.port,
            "log_config": None,
            "lifespan": "on",
        }
        if empire_config.api.secure:
            uvicorn_kwargs["ssl_keyfile"] = str(cert_path / cert_util.KEY_FILENAME)
            uvicorn_kwargs["ssl_certfile"] = str(cert_path / cert_util.CERT_FILENAME)

        uvicorn.run("empire.server.asgi:app", **uvicorn_kwargs)

    sys.exit()
