"""Unit tests for the helpers and orchestration added by `./ps-empire update` (PR #1276).

Covers `overwrite_base_config`, `_detect_release_channel`, `update_empire_source`
branch detection, `_git_fast_forward` per-step error reporting, `_confirm`,
`update_starkiller` / `update_empire_compiler` / `update_plugin_registry`,
the `check_no_foreign_ownership` pre-flight, `run_update`'s aggregation
+ EmpireConfig reload, and `run_setup`'s install-time sync orchestration.
"""

import stat
import subprocess
from types import SimpleNamespace

import pytest
import requests

from empire.server.core.config import data_manager
from empire.server.utils.git_util import GitOperationException


@pytest.fixture
def fake_repo_root(tmp_path):
    """Lay out a minimal repo tree: `.git/` + `setup/checkout-latest-tag.sh`.

    No shipped `config.yaml` — `overwrite_base_config` reads
    `config_manager.DEFAULT_CONFIG`, not anything under this root.
    """
    (tmp_path / ".git").mkdir()
    setup_dir = tmp_path / "setup"
    setup_dir.mkdir()
    script = setup_dir / "checkout-latest-tag.sh"
    script.write_text("#!/bin/bash\nexit 0\n")
    return tmp_path


# ---------- overwrite_base_config ----------


@pytest.fixture
def shipped_config(tmp_path, monkeypatch):
    """Point `DEFAULT_CONFIG` at a template this test owns."""
    src = tmp_path / "shipped-config.yaml"
    src.write_text("starkiller:\n  ref: 4.0-dev\n")
    monkeypatch.setattr(data_manager.config_manager, "DEFAULT_CONFIG", src)
    return src


def test_overwrite_base_config_copies_template(tmp_path, shipped_config, monkeypatch):
    dst = tmp_path / "active-config.yaml"
    dst.write_text("starkiller:\n  ref: stale\n")
    monkeypatch.setattr(data_manager.config_manager, "CONFIG_PATH", dst)

    assert data_manager.overwrite_base_config() is True
    assert dst.read_text() == "starkiller:\n  ref: 4.0-dev\n"


def test_overwrite_base_config_missing_src_returns_false(tmp_path, monkeypatch):
    dst = tmp_path / "active.yaml"
    monkeypatch.setattr(
        data_manager.config_manager, "DEFAULT_CONFIG", tmp_path / "never-shipped.yaml"
    )
    monkeypatch.setattr(data_manager.config_manager, "CONFIG_PATH", dst)

    assert data_manager.overwrite_base_config() is False
    assert not dst.exists()


def test_overwrite_base_config_same_path_skips_copy(shipped_config, monkeypatch):
    monkeypatch.setattr(data_manager.config_manager, "CONFIG_PATH", shipped_config)

    # Should detect that src and dst resolve to the same file and skip the
    # copy without raising shutil.SameFileError.
    assert data_manager.overwrite_base_config() is True


def test_overwrite_base_config_returns_false_on_oserror(
    tmp_path, shipped_config, monkeypatch
):
    dst = tmp_path / "active.yaml"
    monkeypatch.setattr(data_manager.config_manager, "CONFIG_PATH", dst)

    def boom(*_args, **_kwargs):
        raise PermissionError("dst is root-owned")

    monkeypatch.setattr(data_manager.config_manager, "seed_config", boom)

    assert data_manager.overwrite_base_config() is False


# ---------- _detect_release_channel ----------


@pytest.mark.parametrize(
    ("remote_url", "expected"),
    [
        ("git@github.com:BC-SECURITY/Empire-Sponsors.git", "sponsors"),
        ("https://github.com/BC-SECURITY/Empire-Sponsors", "sponsors"),
        ("git@github.com:BC-SECURITY/Empire-Kali.git", "kali"),
        ("https://github.com/BC-SECURITY/Empire.git", None),
    ],
)
def test_detect_release_channel_from_remote_url(
    tmp_path, monkeypatch, remote_url, expected
):
    monkeypatch.setattr(data_manager, "run_as_user", lambda *_a, **_kw: remote_url)
    assert data_manager._detect_release_channel(tmp_path) == expected


def test_detect_release_channel_subprocess_failure_warns_and_returns_none(
    tmp_path, monkeypatch, capsys
):
    """Silent None on subprocess failure would downgrade a sponsors/kali
    install to mainline tags with no greppable breadcrumb — warn loudly."""

    def fail(*_a, **_kw):
        raise subprocess.CalledProcessError(128, ["git", "remote", "get-url", "origin"])

    monkeypatch.setattr(data_manager, "run_as_user", fail)
    assert data_manager._detect_release_channel(tmp_path) is None
    out = capsys.readouterr().out
    assert "could not read 'origin' remote" in out
    assert "treating as mainline" in out


def test_detect_release_channel_empty_stdout_warns_and_returns_none(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(data_manager, "run_as_user", lambda *_a, **_kw: "")
    assert data_manager._detect_release_channel(tmp_path) is None
    out = capsys.readouterr().out
    assert "empty URL" in out
    assert "treating as mainline" in out


# ---------- update_empire_source ----------


def test_update_empire_source_non_git_skips(tmp_path):
    # No .git directory — should banner and return True without subprocess work.
    assert data_manager.update_empire_source(tmp_path) is True


def test_update_empire_source_on_branch_skips_with_warning(fake_repo_root, monkeypatch):
    calls = []

    def fake(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:2] == ["git", "fetch"]:
            return None
        if cmd[:3] == ["git", "branch", "--show-current"]:
            return "sponsors-main"  # non-empty → on a branch
        pytest.fail(f"unexpected call: {cmd}")
        return None

    monkeypatch.setattr(data_manager, "run_as_user", fake)
    assert data_manager.update_empire_source(fake_repo_root) is True
    # The bash script must NOT be invoked when on a branch.
    assert not any("checkout-latest-tag.sh" in " ".join(c) for c in calls)


def test_update_empire_source_detached_runs_checkout_script(
    fake_repo_root, monkeypatch
):
    calls = []

    def fake(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:2] == ["git", "fetch"]:
            return None
        if cmd[:3] == ["git", "branch", "--show-current"]:
            return ""  # empty → detached HEAD
        if cmd[:3] == ["git", "remote", "get-url"]:
            return "git@github.com:BC-SECURITY/Empire-Sponsors.git"
        if cmd[0] == "bash" and "checkout-latest-tag.sh" in cmd[1]:
            assert cmd[-1] == "sponsors", "channel arg should be 'sponsors'"
            return None
        pytest.fail(f"unexpected call: {cmd}")
        return None

    monkeypatch.setattr(data_manager, "run_as_user", fake)
    assert data_manager.update_empire_source(fake_repo_root) is True
    assert any("checkout-latest-tag.sh" in " ".join(c) for c in calls)


def test_update_empire_source_fetch_failure_returns_false(fake_repo_root, monkeypatch):
    def fake(cmd, **kwargs):
        if cmd[:2] == ["git", "fetch"]:
            raise subprocess.CalledProcessError(128, cmd)
        pytest.fail(f"unexpected call: {cmd}")

    monkeypatch.setattr(data_manager, "run_as_user", fake)
    assert data_manager.update_empire_source(fake_repo_root) is False


def test_update_empire_source_missing_script_returns_false(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()  # is a git checkout
    # No setup/checkout-latest-tag.sh

    def fake(cmd, **kwargs):
        if cmd[:2] == ["git", "fetch"]:
            return None
        if cmd[:3] == ["git", "branch", "--show-current"]:
            return ""  # detached
        pytest.fail(f"unexpected call: {cmd}")
        return None

    monkeypatch.setattr(data_manager, "run_as_user", fake)
    assert data_manager.update_empire_source(tmp_path) is False


# ---------- _git_fast_forward per-step error reporting ----------


def test_git_fast_forward_happy_path(tmp_path, monkeypatch):
    target = tmp_path / "starkiller"
    target.mkdir()

    def fake(cmd, **kwargs):
        # `branch --show-current` runs with capture_output=True; everything
        # else (fetch/checkout/pull) runs without.
        if kwargs.get("capture_output"):
            return "main\n"
        return None

    monkeypatch.setattr(data_manager, "run_as_user", fake)
    assert data_manager._git_fast_forward(target, "main", "Starkiller") is True


@pytest.mark.parametrize(
    ("failing_step", "expected_label"),
    [
        ("fetch", "git fetch failed"),
        ("checkout", "git checkout failed"),
        ("pull", "git pull failed"),
    ],
)
def test_git_fast_forward_names_failing_step(
    tmp_path, monkeypatch, capsys, failing_step, expected_label
):
    target = tmp_path / "starkiller"
    target.mkdir()

    def fake(cmd, **kwargs):
        # `branch --show-current` (capture_output=True) reports a branch so
        # the pull step is reached.
        if kwargs.get("capture_output"):
            return "main\n"
        # cmd[1] is the git verb (fetch/checkout/pull) — fail the parametrized one.
        if cmd[1] == failing_step:
            raise subprocess.CalledProcessError(1, cmd)
        return None

    monkeypatch.setattr(data_manager, "run_as_user", fake)
    assert data_manager._git_fast_forward(target, "main", "Starkiller") is False

    captured = capsys.readouterr()
    assert expected_label in captured.out
    assert "Starkiller" in captured.out


def test_git_fast_forward_skips_pull_on_detached_head(tmp_path, monkeypatch, capsys):
    """`ref` may be a tag/SHA — after checkout we land on detached HEAD,
    where `git pull --ff-only` errors out. Skip the pull cleanly."""
    target = tmp_path / "starkiller"
    target.mkdir()
    invoked = []

    def fake(cmd, **kwargs):
        invoked.append(tuple(cmd))
        if kwargs.get("capture_output"):
            # Empty stdout = detached HEAD.
            return ""
        return None

    monkeypatch.setattr(data_manager, "run_as_user", fake)
    assert data_manager._git_fast_forward(target, "v6.5.0", "Starkiller") is True
    assert ("git", "pull", "--ff-only") not in invoked
    assert "detached HEAD" in capsys.readouterr().out


# ---------- _confirm ----------


def test_confirm_assume_yes_returns_true_without_prompting(monkeypatch):
    def boom(*_a, **_kw):
        pytest.fail("input() should not be called when assume_yes=True")

    monkeypatch.setattr("builtins.input", boom)
    assert data_manager._confirm("Migrate?", assume_yes=True) is True


def test_confirm_eof_exits_non_zero(monkeypatch, capsys):
    """Non-TTY without -y must be a hard error, not a silent "no" — otherwise
    CI runs without -y skip migrations and the aggregator exits 0."""

    def raise_eof(_prompt):
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)
    with pytest.raises(SystemExit) as excinfo:
        data_manager._confirm("Migrate?", assume_yes=False)
    assert excinfo.value.code == 2  # noqa: PLR2004 — Unix "misuse of args" convention
    assert "No interactive TTY" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("answer", "expected"),
    [("y", True), ("Y", True), ("yes", True), ("Yes", True), ("n", False), ("", False)],
)
def test_confirm_parses_answer(monkeypatch, answer, expected):
    monkeypatch.setattr("builtins.input", lambda _p: answer)
    assert data_manager._confirm("Migrate?", assume_yes=False) is expected


# ---------- update_starkiller / update_empire_compiler / update_plugin_registry ----------


def test_update_starkiller_existing_checkout_fast_forwards(tmp_path, monkeypatch):
    starkiller_root = tmp_path / "starkiller"
    target = starkiller_root / "4.0-dev"
    (target / ".git").mkdir(parents=True)
    monkeypatch.setattr(data_manager.config_manager, "DATA_DIR", tmp_path)
    # `_git_fast_forward` invokes `branch --show-current` with
    # `capture_output=True`; return a branch so the pull step runs.
    monkeypatch.setattr(
        data_manager,
        "run_as_user",
        lambda *_a, **kw: "4.0-dev\n" if kw.get("capture_output") else None,
    )

    cfg = data_manager.StarkillerConfig(ref="4.0-dev")
    assert data_manager.update_starkiller(cfg, assume_yes=True) is True


def test_update_starkiller_first_run_clones(tmp_path, monkeypatch):
    monkeypatch.setattr(data_manager.config_manager, "DATA_DIR", tmp_path)
    cloned = []

    def fake_sync(cfg):
        cloned.append(cfg.ref)

    monkeypatch.setattr(data_manager, "sync_starkiller", fake_sync)
    cfg = data_manager.StarkillerConfig(ref="4.0-dev")
    assert data_manager.update_starkiller(cfg, assume_yes=True) is True
    assert cloned == ["4.0-dev"]


def test_update_starkiller_cached_other_ref_declined_skips(
    tmp_path, monkeypatch, capsys
):
    starkiller_root = tmp_path / "starkiller"
    (starkiller_root / "sponsors-main").mkdir(parents=True)
    monkeypatch.setattr(data_manager.config_manager, "DATA_DIR", tmp_path)
    monkeypatch.setattr("builtins.input", lambda _p: "n")

    def fake_sync(_cfg):
        pytest.fail("sync_starkiller should not be called when prompt declined")

    monkeypatch.setattr(data_manager, "sync_starkiller", fake_sync)

    cfg = data_manager.StarkillerConfig(ref="4.0-dev")
    assert data_manager.update_starkiller(cfg, assume_yes=False) is True
    assert "migration skipped" in capsys.readouterr().out


def test_update_empire_compiler_directory_override_short_circuits(monkeypatch):
    cfg = data_manager.EmpireCompilerConfig(directory="/tmp/local-compiler")
    # Should not call sync_empire_compiler or _resolve_compiler_platform
    monkeypatch.setattr(
        data_manager,
        "_resolve_compiler_platform",
        lambda: pytest.fail("should not resolve when directory override is set"),
    )
    assert data_manager.update_empire_compiler(cfg, assume_yes=True) is True


def test_update_empire_compiler_already_on_ref_returns_true(tmp_path, monkeypatch):
    compiler_dir = tmp_path / "empire-compiler"
    compiler_dir.mkdir()
    # Match the platform-arch-ref naming scheme produced by sync_empire_compiler.
    monkeypatch.setattr(
        data_manager, "_resolve_compiler_platform", lambda: ("linux", "x64")
    )
    (compiler_dir / "EmpireCompiler-linux-x64-v1.2.3").mkdir()
    monkeypatch.setattr(data_manager.config_manager, "DATA_DIR", tmp_path)

    def fake_sync(_cfg):
        pytest.fail("sync_empire_compiler should not run on cache hit")

    monkeypatch.setattr(data_manager, "sync_empire_compiler", fake_sync)

    cfg = data_manager.EmpireCompilerConfig(repo="r", ref="v1.2.3")
    assert data_manager.update_empire_compiler(cfg, assume_yes=True) is True


def test_update_plugin_registry_no_git_url_returns_true(tmp_path):
    cfg = data_manager.PluginRegistryConfig(
        name="local", location=tmp_path / "registry.yaml"
    )
    assert data_manager.update_plugin_registry(cfg, assume_yes=True) is True


def test_update_plugin_registry_existing_checkout_fast_forwards(tmp_path, monkeypatch):
    base = tmp_path / "plugin-registries" / "marketplace"
    target = base / "main"
    (target / ".git").mkdir(parents=True)
    monkeypatch.setattr(data_manager.config_manager, "DATA_DIR", tmp_path)
    monkeypatch.setattr(
        data_manager,
        "run_as_user",
        lambda *_a, **kw: "main\n" if kw.get("capture_output") else None,
    )

    cfg = data_manager.PluginRegistryConfig(
        name="marketplace", git_url="git://example.com/r.git", ref="main"
    )
    assert data_manager.update_plugin_registry(cfg, assume_yes=True) is True


def test_update_starkiller_clone_failure_returns_false(tmp_path, monkeypatch, capsys):
    """`GitOperationException` from `sync_starkiller` must surface via the
    `[x]` banner and return False — otherwise it propagates past `run_update`
    as a raw traceback, bypassing the aggregator."""
    monkeypatch.setattr(data_manager.config_manager, "DATA_DIR", tmp_path)

    def fail(_cfg):
        raise GitOperationException("clone failed: bad ref")

    monkeypatch.setattr(data_manager, "sync_starkiller", fail)

    cfg = data_manager.StarkillerConfig(ref="4.0-dev")
    assert data_manager.update_starkiller(cfg, assume_yes=True) is False
    out = capsys.readouterr().out
    assert "Starkiller: clone failed" in out
    assert "bad ref" in out


def test_update_empire_compiler_sync_returns_none_is_failure(
    tmp_path, monkeypatch, capsys
):
    """`sync_empire_compiler` returns None (no exception) on unsupported
    arch / missing asset / GitHub API failure. The wrapper must treat that
    as failure — discarding the return value reports "[*] Update complete."
    while the user hits the actual error several layers later."""
    monkeypatch.setattr(data_manager.config_manager, "DATA_DIR", tmp_path)
    monkeypatch.setattr(
        data_manager, "_resolve_compiler_platform", lambda: ("linux", "x64")
    )
    monkeypatch.setattr(data_manager, "sync_empire_compiler", lambda _cfg: None)

    cfg = data_manager.EmpireCompilerConfig(repo="r", ref="v1.2.3")
    assert data_manager.update_empire_compiler(cfg, assume_yes=True) is False
    out = capsys.readouterr().out
    assert "Empire Compiler: sync returned no path" in out


def test_update_empire_compiler_request_failure_returns_false(
    tmp_path, monkeypatch, capsys
):
    """A `requests.RequestException` mid-download (DNS failure, timeout,
    connection reset) must be caught and reported via `[x]`, not propagate."""
    monkeypatch.setattr(data_manager.config_manager, "DATA_DIR", tmp_path)
    monkeypatch.setattr(
        data_manager, "_resolve_compiler_platform", lambda: ("linux", "x64")
    )

    def boom(_cfg):
        raise requests.ConnectionError("simulated DNS failure")

    monkeypatch.setattr(data_manager, "sync_empire_compiler", boom)

    cfg = data_manager.EmpireCompilerConfig(repo="r", ref="v1.2.3")
    assert data_manager.update_empire_compiler(cfg, assume_yes=True) is False
    out = capsys.readouterr().out
    assert "Empire Compiler: download/extract failed" in out
    assert "simulated DNS failure" in out


def test_update_plugin_registry_clone_failure_returns_false(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(data_manager.config_manager, "DATA_DIR", tmp_path)

    def fail(_cfg):
        raise GitOperationException("bad git url")

    monkeypatch.setattr(data_manager, "sync_plugin_registry", fail)

    cfg = data_manager.PluginRegistryConfig(
        name="marketplace", git_url="git://example.com/bad.git", ref="main"
    )
    assert data_manager.update_plugin_registry(cfg, assume_yes=True) is False
    out = capsys.readouterr().out
    assert "Plugin Registry 'marketplace': clone failed" in out
    assert "bad git url" in out


# ---------- pre-flight ownership check ----------


def test_check_no_foreign_ownership_passes_when_user_owned(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "config.yaml"
    config_path.write_text("starkiller:\n  ref: x\n")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(data_manager.config_manager, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(data_manager.config_manager, "CONFIG_PATH", config_path)
    monkeypatch.setattr(data_manager.config_manager, "DATA_DIR", data_dir)

    assert data_manager.check_no_foreign_ownership() is True


def test_check_no_foreign_ownership_blocks_when_root_owned(
    tmp_path, monkeypatch, capsys
):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "config.yaml"
    config_path.write_text("x")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(data_manager.config_manager, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(data_manager.config_manager, "CONFIG_PATH", config_path)
    monkeypatch.setattr(data_manager.config_manager, "DATA_DIR", data_dir)

    # Pretend the current user is uid 99999 — none of the tmp paths match.
    monkeypatch.setattr(data_manager.os, "getuid", lambda: 99999)
    monkeypatch.setenv("USER", "kali")

    assert data_manager.check_no_foreign_ownership() is False
    out = capsys.readouterr().out
    assert "owned by another user" in out
    assert "sudo chown -R kali" in out
    assert str(config_dir) in out
    assert str(data_dir) in out


def test_run_update_aborts_on_foreign_ownership(tmp_path, monkeypatch):
    monkeypatch.setattr(data_manager, "check_no_foreign_ownership", lambda: False)

    def boom(*_a, **_kw):
        pytest.fail("downstream helpers should not run when ownership check fails")

    monkeypatch.setattr(data_manager, "update_empire_source", boom)
    monkeypatch.setattr(data_manager, "overwrite_base_config", boom)

    args = type("Args", (), {"yes": True})()
    # Should return False (caller maps to non-zero exit) without invoking
    # downstream helpers.
    assert data_manager.run_update(args, repo_root=tmp_path) is False


def test_check_no_foreign_ownership_warns_on_unstat_able(tmp_path, monkeypatch, capsys):
    """A path that exists but can't be stat'd must surface a warning, not
    silently pass — otherwise the pre-flight gives false reassurance."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "config.yaml"
    config_path.write_text("x")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(data_manager.config_manager, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(data_manager.config_manager, "CONFIG_PATH", config_path)
    monkeypatch.setattr(data_manager.config_manager, "DATA_DIR", data_dir)

    real_stat = data_manager.Path.stat

    def stat_raises_for_config(self, *args, **kwargs):
        if self == config_path:
            raise PermissionError("simulated EACCES on stat")
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(data_manager.Path, "stat", stat_raises_for_config)

    # Other two paths are user-owned → no foreign-owned, but config_path
    # couldn't be stat'd — we expect True (no foreign found) AND a warning.
    assert data_manager.check_no_foreign_ownership() is True
    assert "Could not stat" in capsys.readouterr().out


def test_check_no_foreign_ownership_falls_back_when_pwd_lookup_fails(
    tmp_path, monkeypatch, capsys
):
    """A uid not present in the passwd database (slim containers, deleted
    accounts) must not crash the pre-flight; fall back to the numeric uid
    in the chown hint."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setattr(data_manager.config_manager, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(
        data_manager.config_manager, "CONFIG_PATH", config_dir / "config.yaml"
    )
    monkeypatch.setattr(data_manager.config_manager, "DATA_DIR", tmp_path / "data")
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(data_manager.os, "getuid", lambda: 99999)
    monkeypatch.delenv("USER", raising=False)

    def raise_keyerror(_uid):
        raise KeyError(99999)

    monkeypatch.setattr(data_manager.pwd, "getpwuid", raise_keyerror)

    assert data_manager.check_no_foreign_ownership() is False
    out = capsys.readouterr().out
    # Numeric uid fallback rather than a crash.
    assert "sudo chown -R 99999" in out


def test_check_no_foreign_ownership_detects_root_owned_starkiller_clone(
    tmp_path, monkeypatch, capsys
):
    """Real-world failure mode: DATA_DIR itself user-owned but a Starkiller
    clone underneath is root-owned — git's dubious-ownership check trips
    later. The pre-flight must catch this."""
    data_dir = tmp_path / "data"
    starkiller_root = data_dir / "starkiller"
    starkiller_clone = starkiller_root / "4.0-dev"
    (starkiller_clone / ".git").mkdir(parents=True)
    monkeypatch.setattr(data_manager.config_manager, "CONFIG_DIR", tmp_path / "config")
    (tmp_path / "config").mkdir()
    monkeypatch.setattr(
        data_manager.config_manager, "CONFIG_PATH", tmp_path / "config" / "config.yaml"
    )
    monkeypatch.setattr(data_manager.config_manager, "DATA_DIR", data_dir)

    real_stat = data_manager.Path.stat

    def stat_with_root_starkiller(self, *args, **kwargs):
        if self == starkiller_clone:
            # Pretend this child is owned by root (uid 0); everything else
            # delegates to the real stat (= current user's uid). `st_mode`
            # carries the directory bit because `_ownership_check_paths`
            # routes children through `is_dir()` before adding them, and on
            # 3.13 `is_dir` reads `S_ISDIR(st_mode)` via the patched `stat`.
            class FakeStat:
                st_mode = stat.S_IFDIR | 0o755
                st_uid = 0

            return FakeStat()
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(data_manager.Path, "stat", stat_with_root_starkiller)

    assert data_manager.check_no_foreign_ownership() is False
    out = capsys.readouterr().out
    assert str(starkiller_clone) in out


# ---------- update_database ----------


@pytest.fixture
def fake_db_base(monkeypatch):
    """Stub out empire.server.core.db.base so update_database can be tested
    without standing up a real database. Tests override individual attrs
    (`pending_migrations`, `backup_db`, `stamp_and_migrate`) as needed.
    """
    from empire.server.core.db import base as base_mod

    # Defaults: already-at-head, never called.
    monkeypatch.setattr(base_mod, "pending_migrations", lambda: ("0003", "0003"))
    monkeypatch.setattr(
        base_mod,
        "backup_db",
        lambda: pytest.fail("backup_db should not be called in this test"),
    )
    monkeypatch.setattr(
        base_mod,
        "stamp_and_migrate",
        lambda: pytest.fail("stamp_and_migrate should not be called in this test"),
    )
    return base_mod


def test_update_database_noop_when_at_head(fake_db_base, capsys):
    """No migration needed — no prompt, no backup, no migrate, success."""
    assert data_manager.update_database(assume_yes=False) is True
    out = capsys.readouterr().out
    assert "schema up to date" in out


def test_update_database_applies_pending_migrations(
    fake_db_base, monkeypatch, capsys, tmp_path
):
    """Pending migrations — backup runs, stamp_and_migrate runs, success."""
    monkeypatch.setattr(fake_db_base, "pending_migrations", lambda: ("0002", "0003"))

    backup_called = []
    migrate_called = []
    backup_path = tmp_path / "empire.db.20260515_120000"

    monkeypatch.setattr(
        fake_db_base, "backup_db", lambda: backup_called.append(True) or backup_path
    )
    monkeypatch.setattr(
        fake_db_base, "stamp_and_migrate", lambda: migrate_called.append(True)
    )

    assert data_manager.update_database(assume_yes=True) is True
    assert backup_called == [True]
    assert migrate_called == [True]
    out = capsys.readouterr().out
    assert "pending migrations" in out
    assert str(backup_path) in out
    assert "migrations complete" in out


def test_update_database_user_declines(fake_db_base, monkeypatch, capsys):
    """User answers 'n' to the prompt — no backup, no migrate, returns False."""
    monkeypatch.setattr(fake_db_base, "pending_migrations", lambda: ("0002", "0003"))
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")

    assert data_manager.update_database(assume_yes=False) is False
    out = capsys.readouterr().out
    assert "skipping migrations" in out


def test_update_database_backup_failure_does_not_block_migration(
    fake_db_base, monkeypatch, capsys
):
    """backup_db returning None should warn but proceed with migration."""
    monkeypatch.setattr(fake_db_base, "pending_migrations", lambda: ("0002", "0003"))
    monkeypatch.setattr(fake_db_base, "backup_db", lambda: None)

    migrate_called = []
    monkeypatch.setattr(
        fake_db_base, "stamp_and_migrate", lambda: migrate_called.append(True)
    )

    assert data_manager.update_database(assume_yes=True) is True
    assert migrate_called == [True]
    out = capsys.readouterr().out
    assert "backup did not produce a file" in out
    assert "migrations complete" in out


def test_update_database_migration_failure_returns_false(
    fake_db_base, monkeypatch, capsys, tmp_path
):
    """stamp_and_migrate raising surfaces an error referencing the backup path."""
    monkeypatch.setattr(fake_db_base, "pending_migrations", lambda: ("0002", "0003"))
    backup_path = tmp_path / "empire.db.20260515_120000"
    monkeypatch.setattr(fake_db_base, "backup_db", lambda: backup_path)

    def boom():
        raise RuntimeError("migration boom")

    monkeypatch.setattr(fake_db_base, "stamp_and_migrate", boom)

    assert data_manager.update_database(assume_yes=True) is False
    out = capsys.readouterr().out
    assert "migration failed" in out
    assert str(backup_path) in out


def test_update_database_revision_check_failure_returns_false(
    fake_db_base, monkeypatch, capsys
):
    """pending_migrations raising should be reported and abort the step."""

    def boom():
        raise RuntimeError("alembic boom")

    monkeypatch.setattr(fake_db_base, "pending_migrations", boom)

    assert data_manager.update_database(assume_yes=True) is False
    out = capsys.readouterr().out
    assert "failed to read Alembic revision state" in out


def test_update_database_untracked_db_labels_correctly(
    fake_db_base, monkeypatch, capsys
):
    """Pre-Alembic DB (current=None) gets an 'untracked → head' label."""
    monkeypatch.setattr(fake_db_base, "pending_migrations", lambda: (None, "0003"))
    monkeypatch.setattr(fake_db_base, "backup_db", lambda: None)
    monkeypatch.setattr(fake_db_base, "stamp_and_migrate", lambda: None)

    assert data_manager.update_database(assume_yes=True) is True
    out = capsys.readouterr().out
    assert "untracked → '0003'" in out


# ---------- run_update orchestration ----------


def test_run_update_aggregates_failures_and_continues_after_source_fail(
    tmp_path, fake_repo_root, monkeypatch, capsys
):
    """Source failure must NOT short-circuit downstream steps; the result
    aggregator must list each failed label."""
    dst = tmp_path / "active.yaml"
    monkeypatch.setattr(data_manager.config_manager, "CONFIG_PATH", dst)

    # Force update_empire_source to return False without doing real git work.
    monkeypatch.setattr(data_manager, "update_empire_source", lambda _root: False)
    # Stub out the downstream helpers so we exercise just the aggregation path.
    monkeypatch.setattr(data_manager, "update_database", lambda *, assume_yes: True)
    monkeypatch.setattr(
        data_manager, "update_starkiller", lambda _cfg, *, assume_yes: True
    )
    monkeypatch.setattr(
        data_manager, "update_empire_compiler", lambda _cfg, *, assume_yes: True
    )
    monkeypatch.setattr(
        data_manager, "update_plugin_registry", lambda _cfg, *, assume_yes: True
    )

    args = type("Args", (), {"yes": True})()
    data_manager.run_update(args, repo_root=fake_repo_root)

    out = capsys.readouterr().out
    assert "Update finished with 1 failure" in out
    assert "Empire source" in out


def test_run_update_reloads_empire_config_after_overwrite(
    tmp_path, fake_repo_root, monkeypatch
):
    """Overwriting the base config must trigger an EmpireConfig reload so
    update_starkiller/update_empire_compiler see the new refs."""
    dst = tmp_path / "active.yaml"
    monkeypatch.setattr(data_manager.config_manager, "CONFIG_PATH", dst)
    monkeypatch.setattr(data_manager, "update_empire_source", lambda _root: True)
    monkeypatch.setattr(data_manager, "update_database", lambda *, assume_yes: True)
    monkeypatch.setattr(
        data_manager, "update_starkiller", lambda _cfg, *, assume_yes: True
    )
    monkeypatch.setattr(
        data_manager, "update_empire_compiler", lambda _cfg, *, assume_yes: True
    )
    monkeypatch.setattr(
        data_manager, "update_plugin_registry", lambda _cfg, *, assume_yes: True
    )

    reloaded = []
    real_cls = data_manager.config_manager.EmpireConfig

    class TrackingEmpireConfig(real_cls):
        def __init__(self, *a, **kw):
            reloaded.append(True)
            super().__init__(*a, **kw)

    monkeypatch.setattr(
        data_manager.config_manager, "EmpireConfig", TrackingEmpireConfig
    )

    args = type("Args", (), {"yes": True})()
    data_manager.run_update(args, repo_root=fake_repo_root)

    assert reloaded, "EmpireConfig was not reloaded after config overwrite"


# ---------- run_setup orchestration ----------


@pytest.fixture
def fake_setup_config(monkeypatch):
    """Minimal `config_manager.empire_config` shape for run_setup.

    Each sync function only reads attributes off the config it's handed,
    so a SimpleNamespace with the right field names is enough — we never
    let the real syncs run (the per-test monkeypatches replace them).
    """
    fake = SimpleNamespace(
        starkiller=SimpleNamespace(ref="v1.0"),
        empire_compiler=SimpleNamespace(),
        plugin_marketplace=SimpleNamespace(
            registries=[SimpleNamespace(name="marketplace")]
        ),
    )
    monkeypatch.setattr(data_manager.config_manager, "empire_config", fake)
    monkeypatch.setattr(data_manager, "check_no_foreign_ownership", lambda: True)
    return fake


def test_run_setup_aborts_on_foreign_ownership(monkeypatch):
    """Pre-flight failure must short-circuit and return None so the caller
    exits non-zero without invoking any sync."""
    monkeypatch.setattr(data_manager, "check_no_foreign_ownership", lambda: False)

    def boom(*_a, **_kw):
        pytest.fail("syncs must not run when ownership pre-flight fails")

    monkeypatch.setattr(data_manager, "sync_starkiller", boom)
    monkeypatch.setattr(data_manager, "sync_empire_compiler", boom)
    monkeypatch.setattr(data_manager, "sync_plugin_registry", boom)

    args = type("Args", (), {})()
    assert data_manager.run_setup(args) is None


def test_run_setup_starkiller_failure_marked_in_results(
    fake_setup_config, monkeypatch, capsys
):
    """A `GitOperationException` from `sync_starkiller` must surface via
    the `[x]` banner and land in the results dict as False — without it,
    `setup` would print nothing about the failure and the next server
    boot would crash trying to mount a missing Starkiller dir."""

    def fail(_cfg):
        raise GitOperationException("clone failed: no SSH key")

    monkeypatch.setattr(data_manager, "sync_starkiller", fail)
    monkeypatch.setattr(data_manager, "sync_empire_compiler", lambda _cfg: object())
    monkeypatch.setattr(data_manager, "sync_plugin_registry", lambda _cfg: object())

    args = type("Args", (), {})()
    results = data_manager.run_setup(args)

    assert results == {
        "Starkiller": False,
        "Empire Compiler": True,
        "Plugin Registry 'marketplace'": True,
    }
    out = capsys.readouterr().out
    assert "Starkiller: clone failed" in out
    assert "no SSH key" in out
    # Failure summary should fire once with the failing label.
    assert "Setup finished with 1 failure" in out
    assert "Starkiller" in out


def test_run_setup_compiler_returns_none_marks_failure(
    fake_setup_config, monkeypatch, capsys
):
    """`sync_empire_compiler` returns None on unsupported arch / missing
    asset / GitHub API failure. Without explicit None handling, setup
    would silently report success and the cold-cache server boot would
    crash with a confusing TypeError in `DotnetCompiler.__init__`."""
    monkeypatch.setattr(data_manager, "sync_starkiller", lambda _cfg: object())
    monkeypatch.setattr(data_manager, "sync_empire_compiler", lambda _cfg: None)
    monkeypatch.setattr(data_manager, "sync_plugin_registry", lambda _cfg: object())

    args = type("Args", (), {})()
    results = data_manager.run_setup(args)

    assert results["Empire Compiler"] is False
    out = capsys.readouterr().out
    assert "Empire Compiler: sync returned no path" in out


def test_run_setup_compiler_request_exception_marks_failure(
    fake_setup_config, monkeypatch, capsys
):
    """`requests.RequestException` mid-download (DNS failure, timeout,
    connection reset) must be caught and reported via `[x]`, not
    propagate as a raw traceback — the install-time analog of the
    update-path fix."""

    def boom(_cfg):
        raise requests.ConnectionError("simulated DNS failure")

    monkeypatch.setattr(data_manager, "sync_starkiller", lambda _cfg: object())
    monkeypatch.setattr(data_manager, "sync_empire_compiler", boom)
    monkeypatch.setattr(data_manager, "sync_plugin_registry", lambda _cfg: object())

    args = type("Args", (), {})()
    results = data_manager.run_setup(args)

    assert results["Empire Compiler"] is False
    out = capsys.readouterr().out
    assert "Empire Compiler: download/extract failed" in out
    assert "simulated DNS failure" in out


def test_run_setup_plugin_registry_failure_marked_per_registry(
    fake_setup_config, monkeypatch, capsys
):
    """Per-registry result keying lets the caller (empire.py) gate
    `_auto_install_plugins` on every configured registry succeeding."""
    fake_setup_config.plugin_marketplace.registries = [
        SimpleNamespace(name="marketplace"),
        SimpleNamespace(name="sponsors"),
    ]

    def fail_for_sponsors(cfg):
        if cfg.name == "sponsors":
            raise GitOperationException("private repo, no SSH key")

    monkeypatch.setattr(data_manager, "sync_starkiller", lambda _cfg: object())
    monkeypatch.setattr(data_manager, "sync_empire_compiler", lambda _cfg: object())
    monkeypatch.setattr(data_manager, "sync_plugin_registry", fail_for_sponsors)

    args = type("Args", (), {})()
    results = data_manager.run_setup(args)

    assert results["Plugin Registry 'marketplace'"] is True
    assert results["Plugin Registry 'sponsors'"] is False
    # Caller-side gating: the dict shape must support a "all registries
    # succeeded?" filter without parsing labels by hand beyond the prefix.
    registries_ok = all(
        ok for label, ok in results.items() if label.startswith("Plugin Registry")
    )
    assert registries_ok is False

    out = capsys.readouterr().out
    assert "Plugin Registry 'sponsors': clone failed" in out
    assert "private repo, no SSH key" in out


def test_run_setup_aggregates_all_failures_in_summary(
    fake_setup_config, monkeypatch, capsys
):
    """Aggregate-then-exit: every sync runs even after earlier failures,
    and the summary lists each failed label so a fresh-install operator
    sees the full picture in one pass."""
    monkeypatch.setattr(
        data_manager,
        "sync_starkiller",
        lambda _cfg: (_ for _ in ()).throw(GitOperationException("starkiller down")),
    )
    monkeypatch.setattr(data_manager, "sync_empire_compiler", lambda _cfg: None)
    monkeypatch.setattr(
        data_manager,
        "sync_plugin_registry",
        lambda _cfg: (_ for _ in ()).throw(GitOperationException("registry down")),
    )

    args = type("Args", (), {})()
    results = data_manager.run_setup(args)

    assert all(ok is False for ok in results.values())
    out = capsys.readouterr().out
    assert "Setup finished with 3 failure(s)" in out
    assert "Starkiller" in out
    assert "Empire Compiler" in out
    assert "Plugin Registry 'marketplace'" in out


def test_run_setup_all_succeed_no_warning_summary(
    fake_setup_config, monkeypatch, capsys
):
    """Happy path: every sync succeeds, results all True, no failure
    summary banner is printed (operators shouldn't see a warning when
    nothing went wrong)."""
    monkeypatch.setattr(data_manager, "sync_starkiller", lambda _cfg: object())
    monkeypatch.setattr(data_manager, "sync_empire_compiler", lambda _cfg: object())
    monkeypatch.setattr(data_manager, "sync_plugin_registry", lambda _cfg: object())

    args = type("Args", (), {})()
    results = data_manager.run_setup(args)

    assert all(results.values())
    out = capsys.readouterr().out
    assert "Setup finished with" not in out
