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

# Anchors for files that ship *inside* the package, as opposed to the
# platformdirs locations below (which hold per-user state). Everything the boot
# path reads out of the package must resolve against these -- resolving against
# the CWD is what made `cd / && empire-server server` fail.
SERVER_ROOT = Path(__file__).resolve().parent.parent.parent
# The directory the `empire` package sits in: the repository root in a git
# checkout, `site-packages` in a wheel install.
REPO_ROOT = SERVER_ROOT.parent.parent


def is_git_checkout() -> bool:
    """Whether Empire is running from a git checkout rather than an install.

    Anchored at ``REPO_ROOT``, never the CWD: a packaged Empire launched from
    inside an unrelated repository must not run git commands against it.
    ``.git`` is a *file* rather than a directory inside a git worktree, so this
    tests existence, not directory-ness.
    """
    return (REPO_ROOT / ".git").exists()


def config_dir(app_name: str) -> Path:
    return Path(platformdirs.user_config_dir(app_name, appauthor=False))


def data_dir(app_name: str) -> Path:
    return Path(platformdirs.user_data_dir(app_name, appauthor=False))


def cache_dir(app_name: str) -> Path:
    return Path(platformdirs.user_cache_dir(app_name, appauthor=False))
