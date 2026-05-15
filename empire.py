#! /usr/bin/env python3

import logging
import sys
from pathlib import Path

from empire import arguments
from empire.server.common import empire
from empire.server.core.config import config_manager
from empire.server.core.config.data_manager import (
    run_setup,
    run_update,
)
from empire.server.core.db import base
from empire.server.core.db.base import SessionLocal
from empire.server.core.exceptions import PluginValidationException
from empire.server.server import run

log = logging.getLogger(__name__)


def _auto_install_plugins(main, auto_install):
    with SessionLocal.begin() as db:
        for entry in auto_install:
            try:
                main.pluginregistriesv2.install_plugin(
                    db, entry.name, entry.version, entry.registry
                )
                log.info(
                    f"Auto-install: plugin '{entry.name}' v{entry.version} installed"
                )
            except PluginValidationException as e:
                log.info(f"Auto-install: skipping '{entry.name}': {e}")
            except Exception:
                log.error(
                    f"Auto-install: failed to install '{entry.name}'",
                    exc_info=True,
                )


if __name__ == "__main__":
    args = arguments.args

    if args.subparser_name == "server":
        run(args)
    if args.subparser_name == "setup":
        results = run_setup(args)
        if results is None:
            # Pre-flight (foreign-ownership) failed; run_setup already
            # printed the actionable banner.
            sys.exit(1)

        auto_install = config_manager.empire_config.plugin_marketplace.auto_install
        # Auto-install reads the registry data populated by
        # sync_plugin_registry. If any registry sync failed, running
        # auto-install would silently produce a partial install — skip
        # with a yellow banner so operators notice in the same scrollback
        # as the [x] errors above.
        registries_ok = all(
            ok for label, ok in results.items() if label.startswith("Plugin Registry")
        )
        if auto_install and not registries_ok:
            print(
                "\x1b[1;33m[!] Skipping plugin auto-install: one or more "
                "plugin registry syncs failed above.\x1b[0m",
                flush=True,
            )
        elif auto_install:
            base.startup_db()
            main = empire.MainMenu(args=args)

            _auto_install_plugins(main, auto_install)

            main.shutdown()

        if not all(results.values()):
            sys.exit(1)

    if args.subparser_name == "update":
        ok = run_update(args, repo_root=Path(__file__).resolve().parent)
        sys.exit(0 if ok else 1)

    sys.exit(0)
