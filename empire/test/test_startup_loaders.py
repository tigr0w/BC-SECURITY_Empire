import fnmatch
import re
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest
import yaml

from empire.server.core.bypass_service import BypassService
from empire.server.core.db import models
from empire.server.core.listener_template_service import ListenerTemplateService
from empire.server.core.profile_service import ProfileService
from empire.server.core.stager_template_service import StagerTemplateService
from empire.server.utils.data_util import ps_convert_to_oneliner
from empire.test.conftest import SERVER_CONFIG_LOC

# Resolved from __file__ rather than cwd: the profile tests enumerate this tree
# to derive what they assert, so a cwd-relative path would turn a missing tree
# into a confusing assertion failure instead of a missing-directory error.
SERVER_DIR = Path(__file__).resolve().parent.parent / "server"
PROFILES_DIR = SERVER_DIR / "data" / "profiles"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LOADER_LOGGER = "empire.server.core.profile_service"

# Guards the tree-derived assertions below against passing vacuously (0 == 0)
# on a vanished tree. Mirrored by the `-gt` floor in the container-structure
# configs, which test_container_structure_configs_check_profiles_shipped pins.
MINIMUM_SHIPPED_PROFILES = 50

CATEGORY_AND_NAME_DEPTH = 2


def _loadable_profiles():
    """Enumerate what the loader would ingest, independently of the loader.

    Both of the loader's skip rules, not just the template one: a profile at
    any other depth is skipped with a warning, and test_vendored_profile_tree_layout
    is what asserts none exists. Modelling only half the rule here would make a
    misplaced profile fail this file's count assertions instead, pointing at the
    loader rather than at the misplaced file.
    """
    return [
        path
        for path in PROFILES_DIR.rglob("*.profile")
        if not fnmatch.fnmatch(path.name, "*template.profile")
        and len(path.relative_to(PROFILES_DIR).parts) == CATEGORY_AND_NAME_DEPTH
    ]


def _loader_records(caplog, levelname):
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelname == levelname and r.name == LOADER_LOGGER
    ]


def test_bypass_loader(monkeypatch):
    sys.argv = ["", "server", "--config", SERVER_CONFIG_LOC]
    session_mock = MagicMock()
    monkeypatch.setattr("empire.server.core.bypass_service.SessionLocal", session_mock)

    session_mock.begin.return_value.__enter__.return_value.scalars.return_value.first.return_value = None

    main_menu = Mock()
    main_menu.install_path = Path("empire/server")

    BypassService(main_menu)

    min_call_count = 4
    assert (
        session_mock.begin.return_value.__enter__.return_value.add.call_count
        > min_call_count
    )


def test_bypass_loader_skips_oneliner_for_non_powershell(monkeypatch):
    """ps_convert_to_oneliner strips newlines, which would corrupt multi-line
    Python bypass scripts. The loader must only apply it to powershell bypasses."""
    sys.argv = ["", "server", "--config", SERVER_CONFIG_LOC]
    session_mock = MagicMock()
    monkeypatch.setattr("empire.server.core.bypass_service.SessionLocal", session_mock)

    session_mock.begin.return_value.__enter__.return_value.scalars.return_value.first.return_value = None

    main_menu = Mock()
    main_menu.install_path = Path("empire/server")

    BypassService(main_menu)

    add_calls = (
        session_mock.begin.return_value.__enter__.return_value.add.call_args_list
    )
    loaded_bypasses = [
        call.args[0]
        for call in add_calls
        if call.args and isinstance(call.args[0], models.Bypass)
    ]
    bypasses_by_name = {b.name: b for b in loaded_bypasses}

    python_yaml = yaml.safe_load(
        Path("empire/server/bypasses/SafeChecksPython.yaml").read_text()
    )
    safechecks_python = bypasses_by_name.get("SafeChecksPython")
    assert safechecks_python is not None, "SafeChecksPython bypass was not loaded"
    assert safechecks_python.language == "python"
    assert safechecks_python.code == python_yaml["script"], (
        "Python bypass script was modified during load — ps_convert_to_oneliner "
        "must not run on non-powershell bypasses"
    )

    ps_yaml = yaml.safe_load(
        Path("empire/server/bypasses/SafeChecksPS.yaml").read_text()
    )
    safechecks_ps = bypasses_by_name.get("SafeChecksPS")
    assert safechecks_ps is not None, "SafeChecksPS bypass was not loaded"
    assert safechecks_ps.language == "powershell"
    assert safechecks_ps.code == ps_convert_to_oneliner(ps_yaml["script"]), (
        "PowerShell bypass script does not match ps_convert_to_oneliner output — "
        "the gate is not invoking the converter"
    )


def test_listener_template_loader(monkeypatch):
    sys.argv = ["", "server", "--config", SERVER_CONFIG_LOC]
    session_mock = MagicMock()
    monkeypatch.setattr(
        "empire.server.core.listener_template_service.SessionLocal", session_mock
    )

    session_mock.begin.return_value.__enter__.return_value.query.return_value.first.return_value.install_path = "empire/server"

    main_menu = Mock()
    main_menu.install_path = Path("empire/server")

    listener_template_service = ListenerTemplateService(main_menu)

    min_template_count = 5
    assert len(listener_template_service.get_listener_templates()) > min_template_count


def test_stager_template_loader(monkeypatch):
    sys.argv = ["", "server", "--config", SERVER_CONFIG_LOC]
    session_mock = MagicMock()
    monkeypatch.setattr(
        "empire.server.core.stager_template_service.SessionLocal", session_mock
    )

    session_mock.begin.return_value.__enter__.return_value.query.return_value.first.return_value.install_path = "empire/server"

    main_menu = Mock()
    main_menu.install_path = Path("empire/server")

    stager_template_service = StagerTemplateService(main_menu)

    min_template_count = 10
    assert len(stager_template_service.get_stager_templates()) > min_template_count


def test_profile_loader(monkeypatch, caplog):
    sys.argv = ["", "server", "--config", SERVER_CONFIG_LOC]
    session_mock = MagicMock()
    monkeypatch.setattr("empire.server.core.profile_service.SessionLocal", session_mock)

    db = session_mock.begin.return_value.__enter__.return_value
    # Empty existing-names set — every on-disk profile is a fresh insert.
    db.scalars.return_value.all.return_value = []

    main_menu = Mock()
    main_menu.install_path = SERVER_DIR

    with caplog.at_level("WARNING", logger=LOADER_LOGGER):
        ProfileService(main_menu)

    # Counted off the tree rather than hardcoded, so adding a profile needs no
    # edit here. Still an independent check: this enumeration and the loader's
    # own are separate code, so it fails if the loader skips anything on disk --
    # a duplicate basename across two categories loads once and trips it.
    loadable = _loadable_profiles()
    assert len(loadable) > MINIMUM_SHIPPED_PROFILES, (
        f"only {len(loadable)} profiles under {PROFILES_DIR}; the tree is missing"
    )
    assert db.add.call_count == len(loadable)

    # The fourth quadrant of the guard's state space: full tree, empty database.
    # Every new install's first boot lands here, so it is the worst place for a
    # false alarm. A guard widened to "not profile_files or not db_existing_names"
    # fires on every fresh install and nothing else in this file catches it.
    noisy = _loader_records(caplog, "ERROR") + _loader_records(caplog, "WARNING")
    assert noisy == [], noisy


def test_profile_loader_warns_on_duplicate(monkeypatch, tmp_path, caplog):
    sys.argv = ["", "server", "--config", SERVER_CONFIG_LOC]
    session_mock = MagicMock()
    monkeypatch.setattr("empire.server.core.profile_service.SessionLocal", session_mock)
    session_mock.begin.return_value.__enter__.return_value.scalars.return_value.all.return_value = []

    profiles_root = tmp_path / "data" / "profiles"
    (profiles_root / "cat_a").mkdir(parents=True)
    (profiles_root / "cat_b").mkdir(parents=True)
    first = profiles_root / "cat_a" / "duplicate.profile"
    second = profiles_root / "cat_b" / "duplicate.profile"
    first.write_text("first body")
    second.write_text("second body")

    main_menu = Mock()
    main_menu.installPath = str(tmp_path)
    main_menu.install_path = tmp_path

    with caplog.at_level("WARNING", logger=LOADER_LOGGER):
        ProfileService(main_menu)

    dup_warnings = [
        r.getMessage()
        for r in caplog.records
        if "Duplicate malleable profile name" in r.getMessage()
    ]
    assert len(dup_warnings) == 1
    assert "duplicate.profile" in dup_warnings[0]
    # Only the first occurrence should be inserted.
    assert session_mock.begin.return_value.__enter__.return_value.add.call_count == 1


def test_profile_loader_names_the_file_that_is_not_utf8(monkeypatch, tmp_path):
    """The bare UnicodeDecodeError carries a byte offset but no filename.

    README.md tells operators to add profiles under a category directory, so a
    file saved as CP1252 is reachable — and it aborts startup. Without the
    path, finding which of 76 files did it means bisecting by hand.
    """
    sys.argv = ["", "server", "--config", SERVER_CONFIG_LOC]
    session_mock = MagicMock()
    monkeypatch.setattr("empire.server.core.profile_service.SessionLocal", session_mock)
    db = session_mock.begin.return_value.__enter__.return_value
    db.scalars.return_value.all.return_value = []

    profiles_root = tmp_path / "data" / "profiles"
    (profiles_root / "Normal").mkdir(parents=True)
    (profiles_root / "Normal" / "cp1252.profile").write_bytes(
        b'set useragent "Caf\xe9 Browser";'
    )

    main_menu = Mock()
    main_menu.install_path = tmp_path

    with pytest.raises(ValueError, match=r"cp1252\.profile"):
        ProfileService(main_menu)


@pytest.mark.parametrize("relative", ["root.profile", "Normal/nested/deep.profile"])
def test_profile_loader_skips_a_misplaced_profile(
    monkeypatch, tmp_path, caplog, relative
):
    """A profile outside <Category>/<name>.profile is skipped, not fatal.

    Unguarded, the depth-1 case IndexErrors out of startup and the depth-3 case
    registers "nested" as the profile name with deep.profile's body.
    """
    sys.argv = ["", "server", "--config", SERVER_CONFIG_LOC]
    session_mock = MagicMock()
    monkeypatch.setattr("empire.server.core.profile_service.SessionLocal", session_mock)
    db = session_mock.begin.return_value.__enter__.return_value
    db.scalars.return_value.all.return_value = []

    misplaced = tmp_path / "data" / "profiles" / relative
    misplaced.parent.mkdir(parents=True)
    misplaced.write_text('set useragent "x";')

    main_menu = Mock()
    main_menu.install_path = tmp_path

    with caplog.at_level("WARNING", logger=LOADER_LOGGER):
        ProfileService(main_menu)

    assert db.add.call_count == 0
    warnings = _loader_records(caplog, "WARNING")
    assert len(warnings) == 1
    assert "<Category>/<name>.profile" in warnings[0]


@pytest.mark.parametrize("tree", ["template_only", "empty", "missing"])
def test_profile_loader_errors_on_empty_tree(monkeypatch, tmp_path, caplog, tree):
    """An unusable profiles directory must fail loudly, not silently succeed.

    This is the failure mode that shipped: archive-based installs had an empty
    data/profiles and the loader logged nothing distinguishable from success.
    Vendoring removes the cause, but the silence itself is what let it reach
    users, so the loader now says so regardless of why the tree is empty.

    "missing" is covered alongside "empty" because rglob on a nonexistent
    directory returns [] rather than raising, so it reaches the same guard.
    """
    sys.argv = ["", "server", "--config", SERVER_CONFIG_LOC]
    session_mock = MagicMock()
    monkeypatch.setattr("empire.server.core.profile_service.SessionLocal", session_mock)
    db = session_mock.begin.return_value.__enter__.return_value
    db.scalars.return_value.all.return_value = []

    profiles_root = tmp_path / "data" / "profiles"
    if tree != "missing":
        profiles_root.mkdir(parents=True)
    if tree == "template_only":
        # A lone template is still an unusable install: the loader skips
        # templates, so this must count as empty rather than as one profile.
        (profiles_root / "template.profile").write_text("template body")

    main_menu = Mock()
    main_menu.install_path = tmp_path

    with caplog.at_level("ERROR", logger=LOADER_LOGGER):
        ProfileService(main_menu)

    errors = _loader_records(caplog, "ERROR")
    assert len(errors) == 1
    # Both branches open with "No malleable profiles found", so match on the
    # cold-install half too — otherwise a swap of the two messages passes here
    # and tells an operator with no database to go rescue rows that don't exist.
    assert "No malleable profiles found" in errors[0]
    assert "none in the database" in errors[0]
    assert db.add.call_count == 0


def test_profile_loader_reports_db_count_when_tree_is_lost(
    monkeypatch, tmp_path, caplog
):
    """An empty tree with a warm database gets its own message.

    The database is then the only surviving copy, and POST
    /malleable-profiles/reset would delete it and reload nothing, so the
    operator needs to be told that specifically rather than that listeners
    "have none to select" — which would be false here.
    """
    sys.argv = ["", "server", "--config", SERVER_CONFIG_LOC]
    session_mock = MagicMock()
    monkeypatch.setattr("empire.server.core.profile_service.SessionLocal", session_mock)
    db = session_mock.begin.return_value.__enter__.return_value
    db.scalars.return_value.all.return_value = [
        "jquery-c2.4.2.profile",
        "trevor.profile",
    ]

    (tmp_path / "data" / "profiles").mkdir(parents=True)

    main_menu = Mock()
    main_menu.install_path = tmp_path

    with caplog.at_level("WARNING", logger=LOADER_LOGGER):
        ProfileService(main_menu)

    errors = _loader_records(caplog, "ERROR")
    assert len(errors) == 1
    assert "the 2 already in the database are now the only copy" in errors[0]
    assert db.add.call_count == 0


def test_profile_loader_silent_on_restart_against_populated_db(monkeypatch, caplog):
    """A restart against an already-populated database must stay silent.

    This is what pins the file-count-vs-row-count distinction. Every profile is
    already in the DB, so nothing is inserted — a guard written against rows
    inserted rather than files on disk would report a healthy install as empty
    on every single boot after the first.

    Captures at WARNING and asserts on both levels, so that moving the guard
    down to WARNING cannot silently disarm this test.
    """
    sys.argv = ["", "server", "--config", SERVER_CONFIG_LOC]
    session_mock = MagicMock()
    monkeypatch.setattr("empire.server.core.profile_service.SessionLocal", session_mock)

    already_loaded = [p.name for p in _loadable_profiles()]
    assert already_loaded, "fixture is vacuous if the vendored tree is missing"
    db = session_mock.begin.return_value.__enter__.return_value
    db.scalars.return_value.all.return_value = already_loaded

    main_menu = Mock()
    main_menu.install_path = SERVER_DIR

    with caplog.at_level("WARNING", logger=LOADER_LOGGER):
        ProfileService(main_menu)

    assert db.add.call_count == 0
    noisy = _loader_records(caplog, "ERROR") + _loader_records(caplog, "WARNING")
    assert noisy == [], noisy


def test_vendored_profile_tree_layout():
    """Pin the on-disk shape of the vendored profiles tree.

    ProfileService.load_malleable_profiles skips anything that is not
    <Category>/<name>.profile, so a misplaced file ships without ever loading.
    template.profile is the sole depth-1 file and is skipped a step earlier, by
    the fnmatch(filename, "*template.profile") guard.

    The template check is by name, not by a count of files. A contributed
    my-template.profile matches the loader's glob too, so it would be skipped
    and never load; naming the one file allowed to be skipped catches that
    without a total that has to be bumped every time a profile is added.
    """
    all_profiles = sorted(PROFILES_DIR.rglob("*.profile"))

    skipped = sorted(
        p.name for p in all_profiles if fnmatch.fnmatch(p.name, "*template.profile")
    )
    assert skipped == ["template.profile"], (
        f"the loader skips every *template.profile, so {skipped} would never load"
    )

    relative_parts = [p.relative_to(PROFILES_DIR).parts for p in all_profiles]

    depth_one = [parts for parts in relative_parts if len(parts) == 1]
    assert depth_one == [("template.profile",)]

    misplaced = [
        "/".join(parts)
        for parts in relative_parts
        if len(parts) != CATEGORY_AND_NAME_DEPTH and parts != ("template.profile",)
    ]
    assert not misplaced, (
        f"profiles must live at <Category>/<name>.profile; found: {misplaced}"
    )


@pytest.mark.skipif(
    not (REPO_ROOT / ".git").exists() or shutil.which("git") is None,
    reason="reads the git index; not meaningful outside a checkout",
)
def test_third_party_license_texts_ship():
    """Keep the license texts inside the blanket *.txt rule's exemption.

    Two assertions because one cannot cover both halves: git ignores nothing
    that is already tracked, so the negation at the bottom of .gitignore is
    load-bearing only for files not yet in the index.

    The index check catches a text being deleted or renamed. The probe catches
    the negation being dropped or reordered — which leaves these three files
    tracked and green while silently refusing the next license text added
    beside a newly vendored profile.
    """
    required = [
        "empire/server/data/profiles/NOTICE.md",
        "empire/server/data/profiles/LICENSES/GPL-3.0.txt",
        "empire/server/data/profiles/LICENSES/BSD-3-Clause-bluscreenofjeff.txt",
    ]
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", *required],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert tracked.returncode == 0, (
        f"third-party license texts are not tracked by git: {tracked.stderr}"
    )

    probe = "empire/server/data/profiles/LICENSES/__probe__.txt"
    ignored = subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", probe],
        cwd=REPO_ROOT,
        check=False,
    )
    assert ignored.returncode == 1, (
        f"{probe} would be gitignored, so a new license text could not be added: "
        "the *.txt negation in .gitignore was dropped or reordered"
    )


CST_CONFIGS = [
    REPO_ROOT / ".github" / "cst-config-docker.yaml",
    REPO_ROOT / ".github" / "install_tests" / "cst-config-install-base.yaml",
]


@pytest.mark.skipif(
    not (REPO_ROOT / ".github").is_dir(),
    reason=".github is not part of the packaged tree (.dockerignore drops it, "
    "and the Docker test job runs this suite from inside the image)",
)
@pytest.mark.parametrize("config_path", CST_CONFIGS, ids=lambda p: p.name)
def test_container_structure_configs_check_profiles_shipped(config_path):
    """Keep an artifact-level profiles check in both container configs.

    Neither config is exercised on an ordinary profile-adding PR. test_image is
    gated off at the job level unless the branch is release/* or carries the
    docker label. test_install_script does run, but its build and test steps
    are skipped unless setup/install.sh, poetry.lock or .github/install_tests
    changed, or the branch is release/*. Checking them here — in a job that
    runs unconditionally — is what stops the guard being deleted, or being
    tightened back into an exact count that only fails at release time.
    """
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    checks = [t for t in config["commandTests"] if t["name"] == "profiles-shipped"]
    assert len(checks) == 1, f"expected one profiles-shipped test in {config_path}"

    # The check is only meaningful if the command still measures the same thing.
    command = " ".join(checks[0]["args"])
    assert "empire/server/data/profiles" in command
    assert "*.profile" in command

    floor_match = re.search(r"-gt (\d+)", command)
    assert floor_match, (
        f"the profiles check in {config_path} is not a floor, so adding a "
        f"profile will fail it at release time: {command}"
    )

    # Catches a floor set at or above the real tree, which would fail the
    # release job on a complete image. A relation, so it needs no maintenance.
    on_disk = len(list(PROFILES_DIR.rglob("*.profile")))
    assert int(floor_match.group(1)) < on_disk, (
        f"floor {floor_match.group(1)} is not below the {on_disk} profiles on "
        f"disk, so {config_path} would fail on a complete tree"
    )


def test_vendored_profiles_are_utf8_and_some_are_non_ascii():
    """Pin the data precondition behind the loader's explicit utf-8 read.

    Some vendored profiles carry non-ASCII bytes, so reading them at the
    locale default is only safe while that default is utf-8. PEP 540 makes it
    so in most environments, but not under PYTHONUTF8=0 with a non-utf-8
    locale, which is why profile_service passes encoding explicitly.

    This pins the data, not the call: it would stay green if the encoding
    argument were dropped, because the interpreter default masks it almost
    everywhere. What it does catch is a profile arriving in another encoding.
    Both halves matter — the files must decode as utf-8, and at least one must
    be non-ASCII, or the explicit encoding stops being load-bearing.
    """
    undecodable = []
    non_ascii = []
    for path in sorted(PROFILES_DIR.rglob("*.profile")):
        raw = path.read_bytes()
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            undecodable.append(path.name)
            continue
        if not raw.isascii():
            non_ascii.append(path.name)

    assert not undecodable, f"loader reads these with encoding='utf-8': {undecodable}"
    assert non_ascii, (
        "no non-ASCII profile remains, so the explicit utf-8 read is no longer "
        "load-bearing and this test would pass vacuously"
    )
