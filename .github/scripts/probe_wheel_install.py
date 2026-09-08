"""Assert a wheel-installed Empire finds its own files, from any directory.

Runs inside the venv the wheel was installed into. ``check_wheel.py`` proves
the assets are in the zip; this proves the installed package resolves them on
disk, and that the console script reaches ``empire.main``.

The venv is installed ``--no-deps`` (the ``test_wheel`` workflow explains why
that is sufficient), so only stdlib, ``empire``'s stdlib-only modules, and
``platformdirs`` are importable here.
"""

import subprocess
import sys
from pathlib import Path

from check_wheel import (
    MIN_MODULE_SOURCE_PS1,
    MIN_PROFILES,
    MIN_YAML,
    REQUIRED_MEMBERS,
)

from empire.server.core.config import paths

REFUSAL_TEXT = "only available from a git checkout"

# Debian and its derivatives rename the interpreter's package directory, and a
# downstream packager rerunning this probe is exactly who it is here for.
INSTALL_DIR_NAMES = frozenset({"site-packages", "dist-packages"})


def _asset_failures() -> list[str]:
    server_root = paths.SERVER_ROOT

    # Run from a checkout, everything below passes against the source tree
    # without the wheel being involved at all.
    if INSTALL_DIR_NAMES.isdisjoint(server_root.parts):
        return [f"probing a checkout, not an install: SERVER_ROOT={server_root}"]

    failures = [
        f"{member} did not survive the install"
        for member in REQUIRED_MEMBERS
        if not (paths.REPO_ROOT / member).is_file()
    ]

    counts = (
        (len(list(server_root.rglob("*.yaml"))), MIN_YAML, "yaml under empire/server"),
        (
            len(list((server_root / "data/module_source").rglob("*.ps1"))),
            MIN_MODULE_SOURCE_PS1,
            ".ps1 under data/module_source",
        ),
        (
            len(list((server_root / "data/profiles").rglob("*.profile"))),
            MIN_PROFILES,
            ".profile under data/profiles",
        ),
    )
    failures += [
        f"only {count} {label} (expected >= {minimum})"
        for count, minimum, label in counts
        if count < minimum
    ]

    if paths.is_git_checkout():
        failures.append(
            f"is_git_checkout() is true for an install -- {paths.REPO_ROOT}/.git "
            "shipped in the wheel, and the server will run git against it"
        )

    return failures


def _console_script_failures() -> list[str]:
    script = Path(sys.executable).parent / "empire-server"
    if not script.is_file():
        return [f"{script} was not installed"]

    # `install` is the one subcommand that returns without building a server,
    # so it is the cheapest proof that the script reaches empire.main.
    result = subprocess.run(
        [script, "install"], capture_output=True, text=True, check=False
    )
    if result.returncode != 1 or REFUSAL_TEXT not in result.stderr:
        return [
            f"`empire-server install` exited {result.returncode}, expected 1 with "
            f"{REFUSAL_TEXT!r} on stderr\n"
            f"    stdout: {result.stdout.strip()}\n"
            f"    stderr: {result.stderr.strip()}"
        ]
    return []


def main() -> int:
    failures = _asset_failures() + _console_script_failures()

    if failures:
        print("wheel install probe FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print(f"wheel install OK: assets resolve under {paths.SERVER_ROOT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
