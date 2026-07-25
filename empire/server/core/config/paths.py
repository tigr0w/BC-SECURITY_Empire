r"""Empire's base directories via platformdirs.

A side-effect-free leaf module: it only *computes* paths, never creates them and
never imports the rest of the config machinery. This lets both ``config_manager``
and the root ``conftest.py`` derive their directories from a single source of the
``platformdirs`` incantation, even though ``conftest`` must not import
``config_manager`` at pytest startup (that import has mkdir/config-copy side
effects — see ``conftest._reset_test_dirs``).

``appauthor=False`` avoids the doubled ``empire\empire`` on Windows and is ignored
on Linux/macOS. On Linux these honor ``$XDG_CONFIG_HOME`` / ``$XDG_DATA_HOME`` /
``$XDG_CACHE_HOME``; on macOS/Windows they resolve to the native locations.

Caution: these three are pairwise distinct only on Linux. On macOS and Windows
``config_dir`` and ``data_dir`` are the *same* directory, and on Windows
``cache_dir`` sits inside both. Never delete one wholesale expecting the others
to survive.
"""

from pathlib import Path

import platformdirs

# The files Empire seeds into config_dir(); deleting these by name is how a
# caller clears it without tripping the collision above.
CONFIG_FILENAME = "config.yaml"
USER_CONFIG_FILENAME = "config.user.yaml"
SEEDED_CONFIG_FILENAMES = (CONFIG_FILENAME, USER_CONFIG_FILENAME)


def config_dir(app_name: str) -> Path:
    return Path(platformdirs.user_config_dir(app_name, appauthor=False))


def data_dir(app_name: str) -> Path:
    return Path(platformdirs.user_data_dir(app_name, appauthor=False))


def cache_dir(app_name: str) -> Path:
    return Path(platformdirs.user_cache_dir(app_name, appauthor=False))
