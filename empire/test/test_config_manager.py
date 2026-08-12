"""Regression tests for empire.server.core.config.config_manager."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from empire.server.core.config import paths
from empire.server.core.config.config_manager import (
    CONFIG_PATH,
    DATA_DIR,
    DEFAULT_CONFIG,
    DEFAULT_USER_CONFIG,
    EmpireConfig,
    seed_config,
)
from empire.test.conftest import SERVER_CONFIG_LOC


def test_config_manager_import_does_not_wipe_data_dir():
    """Importing config_manager in a TEST_MODE subprocess must NOT delete
    pre-existing DATA_DIR contents.

    Regression for the bug fixed by the
    2026-05-26-test-mode-data-dir-wipe spec: the rmtree at config_manager
    module-import time used to nuke the EmpireCompiler cache the parent
    pytest process had just downloaded, defeating the
    `empire_base_url` perf-test fixture's reuse of that cache.
    """
    assert os.environ.get("TEST_MODE"), (
        "TEST_MODE must be set for this test to exercise the wipe path. "
        "Run via pytest (which reads pytest.ini's `env = TEST_MODE=true`), "
        "not bare python."
    )

    sentinel = DATA_DIR / "test_config_manager_sentinel.txt"
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    try:
        sentinel.write_text("must_survive")
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import empire.server.core.config.config_manager",
            ],
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, (
            f"subprocess crashed during config_manager import:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert sentinel.exists(), (
            "config_manager module import wiped DATA_DIR (regression "
            "of the 2026-05-26 spec). The wipe must live only in "
            "root conftest.py::_reset_test_dirs."
        )
    finally:
        sentinel.unlink(missing_ok=True)


def test_config_tolerates_stale_submodules_key():
    """A config.yaml written before the submodule removal must still load.

    EmpireConfig sets extra="allow", so the now-unknown key is ignored rather
    than rejected. Without this, removing the field would be a breaking change
    for every existing install.
    """
    config = EmpireConfig.model_validate({"submodules": {"auto_update": True}})

    assert config.database.use  # the rest of the model still populates


def test_config_tolerates_stale_submodules_key_on_disk(tmp_path):
    """The same, through the real --config path rather than model_validate.

    model_validate bypasses settings_customise_sources, so on its own it does
    not show that an operator's existing config.yaml still boots — which is
    the compatibility claim the changelog actually makes.

    Runs in a subprocess for the same reason as the DATA_DIR test above:
    building a second EmpireConfig in-process disturbs module state that the
    session-scoped app fixture depends on, which shows up as unrelated
    collection errors across the API suites. A fresh interpreter also means
    _module_base_config_path is resolved from this process's own argv rather
    than left set by an earlier test, so this exercises the resolution an
    operator actually gets.
    """
    base = yaml.safe_load(Path(SERVER_CONFIG_LOC).read_text(encoding="utf-8"))
    base["submodules"] = {"auto_update": True}
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.safe_dump(base), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from empire.server.core.config.config_manager import EmpireConfig;"
            "c = EmpireConfig();"
            "print('EXTRA:', c.model_extra.get('submodules'));"
            "print('DB:', c.database.use)",
            "server",
            "--config",
            str(config_file),
        ],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        f"config carrying a stale submodules key failed to load:\n{result.stderr}"
    )
    assert "EXTRA: {'auto_update': True}" in result.stdout, result.stdout
    assert "DB:" in result.stdout


def test_default_config_paths_are_absolute_and_inside_the_package():
    """Regression for the CWD-relative `Path("empire/server") / ...` default.

    This resolved against the launch directory, so importing config_manager
    from anywhere but the repo root raised FileNotFoundError before argparse
    ever ran.
    """
    assert DEFAULT_CONFIG.is_absolute()
    assert DEFAULT_CONFIG == paths.SERVER_ROOT / paths.CONFIG_FILENAME
    assert DEFAULT_CONFIG.exists()

    assert DEFAULT_USER_CONFIG.is_absolute()
    assert DEFAULT_USER_CONFIG == paths.SERVER_ROOT / paths.USER_CONFIG_FILENAME


def test_default_config_still_resolves_from_an_unrelated_cwd(monkeypatch, tmp_path):
    """`cd / && empire-server server` must still find the shipped template.

    Deliberately an in-process assertion rather than a subprocess import: the
    seeding copy at import time only runs `if not CONFIG_PATH.exists()`, so
    under TEST_MODE with a config already seeded, a subprocess import would
    succeed even with the bug present and prove nothing.
    """
    monkeypatch.chdir(tmp_path)

    assert DEFAULT_CONFIG.exists(), (
        f"{DEFAULT_CONFIG} does not resolve from {tmp_path} — it is CWD-relative"
    )


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores the mode either way")
def test_seed_config_does_not_carry_a_read_only_source_mode(tmp_path):
    """`shutil.copy` is copyfile + copymode; a packaged config.yaml is 0444.

    The source has to be made read-only here for this to test anything. A
    checkout's config.yaml is 0644, so `copy` and `copyfile` are
    indistinguishable against it, and asserting on the already-seeded
    CONFIG_PATH passes with the bug fully present.
    """
    source = tmp_path / "config.yaml"
    source.write_text("suppress_self_cert_warning: true\n")
    source.chmod(0o444)
    destination = tmp_path / "seeded.yaml"

    seed_config(source, destination)

    assert destination.stat().st_mode & 0o200, (
        f"seeded config is not writable by its owner "
        f"({destination.stat().st_mode & 0o777:#o}) — copymode carried 0444 across"
    )
    assert destination.read_text() == source.read_text()


def test_config_is_seeded_at_import_time():
    assert CONFIG_PATH.exists(), "config_manager seeds this at import time"
