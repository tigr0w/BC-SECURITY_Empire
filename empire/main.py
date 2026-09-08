"""Subcommand dispatcher for the `empire-server` console script.

Lives inside the package rather than in root `empire.py` because
`empire/__init__.py` shadows a same-named root module, so `empire:main` is
unreachable from an installed distribution. Root `empire.py` is a shim onto
this module, keeping `./ps-empire` working from a checkout.
"""

import logging
import sys

from empire import arguments

log = logging.getLogger(__name__)


def _auto_install_plugins(menu, auto_install):
    from empire.server.core.db.base import SessionLocal
    from empire.server.core.exceptions import PluginValidationException

    with SessionLocal.begin() as db:
        for entry in auto_install:
            try:
                menu.pluginregistriesv2.install_plugin(
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


def main():
    args = arguments.parse_args()

    if args.subparser_name == "install":
        # `install` is bash-only (ps-empire -> setup/install.sh). The console
        # script advertises it in --help on channels that ship no
        # setup/install.sh, where it used to fall through to sys.exit(0).
        print(
            "\x1b[1;31m[!] 'install' is only available from a git checkout, via "
            "'./ps-empire install'. Install Empire through your package manager "
            "instead.\x1b[0m",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)

    # Deferred: these all pull in db.base, which builds the engine at import
    # time and, for MySQL, connects. At module scope that runs before the
    # `install` refusal above -- exactly the case the refusal exists for.
    from empire.server.common import empire
    from empire.server.core.config import config_manager, paths
    from empire.server.core.config.data_manager import run_setup, run_update
    from empire.server.core.db import base
    from empire.server.server import run

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
            menu = empire.MainMenu()

            _auto_install_plugins(menu, auto_install)

            menu.shutdown()

        if not all(results.values()):
            sys.exit(1)

    if args.subparser_name == "update":
        ok = run_update(args, repo_root=paths.REPO_ROOT)
        sys.exit(0 if ok else 1)

    sys.exit(0)
