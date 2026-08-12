"""Assert a built wheel actually contains a working Empire.

Guards the two regressions that made an installed Empire non-functional:
`packages` dropping every non-Python asset, and the missing console-script
entry point. The asset checks span several classes (yaml, ps1, single files)
because a `packages` change can drop one directory tree and not the others.

Build a wheel (`poetry build --format wheel`) then run this script; it finds
`dist/` at the repo root, so the CWD does not matter.
"""

import configparser
import sys
import zipfile
from pathlib import Path

SERVER_PREFIX = "empire/server/"
MODULE_SOURCE_PREFIX = "empire/server/data/module_source/"
PROFILES_PREFIX = "empire/server/data/profiles/"

# Floors, well below both trees (sponsors ships 559 yaml / 138 ps1, public
# 509 / 139) since this job runs on every PR in both. They catch "shipped
# none of them", which is what the `**/*.py` glob did.
MIN_YAML = 400
MIN_MODULE_SOURCE_PS1 = 100
# The same number the two container-structure configs use, though they spell it
# `-gt` and this one passes at exactly 50; both sit far below the ~75 shipped,
# so the boundary never decides anything. A bare "is it zero" check would pass a
# wheel carrying a single profile, which is the shape a botched exclude leaves.
MIN_PROFILES = 50

# Single files a count-based floor would never miss the loss of, and without
# which a server cannot start (config) or compile (confuser).
#
# The last three are a redistribution obligation rather than a runtime one.
# NOTICE.md states that it and the LICENSES/ texts accompany the profiles in
# every distribution, and they reach the wheel only via a negation of the
# blanket `*.txt` rule in .gitignore -- poetry drops VCS-ignored files, so
# reordering that negation would ship a wheel whose own NOTICE.md is false
# while every .profile check here still passes.
REQUIRED_MEMBERS = (
    "empire/server/config.yaml",
    "empire/server/data/confuser.crproj",
    "empire/server/data/profiles/NOTICE.md",
    "empire/server/data/profiles/LICENSES/GPL-3.0.txt",
    "empire/server/data/profiles/LICENSES/BSD-3-Clause-bluscreenofjeff.txt",
)

WHEEL_GLOB = "empire_bc_security_fork-*.whl"

DIST_DIR = Path(__file__).resolve().parents[2] / "dist"


def _count(names: list[str], prefix: str, suffix: str) -> int:
    return sum(1 for n in names if n.startswith(prefix) and n.endswith(suffix))


def _asset_failures(names: list[str]) -> list[str]:
    failures = []

    yaml_count = _count(names, SERVER_PREFIX, ".yaml")
    if yaml_count < MIN_YAML:
        failures.append(
            f"only {yaml_count} yaml files under {SERVER_PREFIX} "
            f"(expected >= {MIN_YAML}); is `packages` still a *.py glob?"
        )

    # The yaml floor alone passes a wheel with every module definition and
    # none of the payloads they run -- invisible at boot, because
    # module_service skips a module whose script_path is missing and the API
    # still serves a full-looking catalogue.
    ps1_count = _count(names, MODULE_SOURCE_PREFIX, ".ps1")
    if ps1_count < MIN_MODULE_SOURCE_PS1:
        failures.append(
            f"only {ps1_count} .ps1 under {MODULE_SOURCE_PREFIX} "
            f"(expected >= {MIN_MODULE_SOURCE_PS1}); modules would load from "
            "yaml and then fail at execution time"
        )

    failures += [
        f"{m} is missing from the wheel" for m in REQUIRED_MEMBERS if m not in names
    ]

    profile_count = _count(names, PROFILES_PREFIX, ".profile")
    if profile_count < MIN_PROFILES:
        failures.append(
            f"only {profile_count} .profile files (expected >= {MIN_PROFILES}) -- "
            "the vendored tree did not reach the wheel. A server built from this "
            "still starts: profile_service logs the empty tree at ERROR, and on a "
            "fresh database malleable listeners have none to select."
        )

    leaked_tests = [n for n in names if n.startswith("empire/test/")]
    if leaked_tests:
        failures.append(
            f"empire/test/ leaked into the wheel ({len(leaked_tests)} files); "
            "check `exclude` in pyproject.toml"
        )

    return failures


def _entry_point_failures(names: list[str], entry_points: str | None) -> list[str]:
    if entry_points is None:
        return ["no entry_points.txt -- [tool.poetry.scripts] is missing"]

    parser = configparser.ConfigParser()
    parser.read_string(entry_points)
    target = parser.get("console_scripts", "empire-server", fallback=None)
    if target is None:
        return [f"entry_points.txt declares no empire-server script:\n{entry_points}"]

    # A declared name proves nothing about whether the module it points at
    # shipped -- a gap that would otherwise surface only in a downstream
    # packager's hands.
    module_file = target.split(":")[0].replace(".", "/") + ".py"
    if module_file not in names:
        return [f"entry point targets {target}, but {module_file} is not in the wheel"]

    return []


def main() -> int:
    wheels = sorted(DIST_DIR.glob(WHEEL_GLOB))
    if len(wheels) != 1:
        print(
            f"expected exactly one {WHEEL_GLOB} in dist/, "
            f"found {[w.name for w in wheels]}"
        )
        return 1

    wheel = wheels[0]
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
        entry_point_files = [
            n for n in names if n.endswith(".dist-info/entry_points.txt")
        ]
        entry_points = (
            zf.read(entry_point_files[0]).decode() if entry_point_files else None
        )

    failures = _asset_failures(names) + _entry_point_failures(names, entry_points)

    if failures:
        print(f"wheel check FAILED for {wheel.name}:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print(
        f"wheel OK: {wheel.name} "
        f"({_count(names, SERVER_PREFIX, '.yaml')} yaml, "
        f"{_count(names, MODULE_SOURCE_PREFIX, '.ps1')} ps1, "
        f"{_count(names, PROFILES_PREFIX, '.profile')} profiles, "
        f"{len(names)} files)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
