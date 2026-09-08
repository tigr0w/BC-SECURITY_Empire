import signal
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from empire.server import server
from empire.server.core.config import paths


def _stub_subprocess(monkeypatch, run):
    """Swap `server`'s view of `subprocess`, not the module's own `run`.

    `monkeypatch.setattr(server.subprocess, "run", ...)` reaches through to the
    global module object, so any Empire background thread alive in this worker
    (the session-scoped app boots listeners and plugins) would get the stub
    too. Rebinding the name inside `server` keeps the blast radius to the
    module under test.
    """
    monkeypatch.setattr(
        server,
        "subprocess",
        SimpleNamespace(
            run=run,
            PIPE=subprocess.PIPE,
            DEVNULL=subprocess.DEVNULL,
        ),
    )


def test_clean_wipes_config_data_and_cache(monkeypatch):
    """`server --clean` must wipe CONFIG_DIR, DATA_DIR, and CACHE_DIR.

    The CACHE_DIR wipe is load-bearing now that the cache lives outside DATA_DIR
    (platformdirs migration, #960); previously ``rmtree(DATA_DIR)`` covered it.
    """
    removed: list[Path] = []
    monkeypatch.setattr(server.shutil, "rmtree", lambda p, **k: removed.append(Path(p)))
    monkeypatch.setattr(server.base, "reset_db", lambda: None)

    server.clean()

    assert set(removed) == {server.CONFIG_DIR, server.DATA_DIR, server.CACHE_DIR}


def test_get_commit_sha_is_inert_when_not_a_checkout(monkeypatch):
    """A wheel install must not shell out to git for the version.

    Named for the one function it drives. The broader claim -- that a package
    install shells out to git nowhere on the boot path -- is asserted through
    server.run() in test_run_derives_ssl_kwargs_from_cert_util_constants.
    """
    monkeypatch.setattr(paths, "is_git_checkout", lambda: False)
    monkeypatch.delenv("EMPIRE_COMMIT_SHA", raising=False)

    def _explode(*args, **kwargs):
        raise AssertionError(f"git must not run on a package install: {args}")

    _stub_subprocess(monkeypatch, _explode)

    assert server.get_commit_sha() == "unknown"


def test_get_commit_sha_runs_git_in_the_repo_root_not_the_cwd(monkeypatch, tmp_path):
    """Every git invocation get_commit_sha makes must be pinned to REPO_ROOT.

    `git rev-parse --short HEAD` with cwd=None reports the HEAD of whatever
    repository the operator happened to launch from as Empire's own version.
    """
    launch_dir = tmp_path / "someone-elses-repo"
    (launch_dir / ".git").mkdir(parents=True)
    monkeypatch.chdir(launch_dir)
    monkeypatch.setattr(paths, "is_git_checkout", lambda: True)
    monkeypatch.delenv("EMPIRE_COMMIT_SHA", raising=False)

    calls: list[dict] = []

    def _record_run(command, **kwargs):
        calls.append({"command": command, "cwd": kwargs.get("cwd")})
        return subprocess.CompletedProcess(command, 0, stdout="deadbee\n", stderr="")

    _stub_subprocess(monkeypatch, _record_run)

    assert server.get_commit_sha() == "deadbee"

    # Every recorded call, not a fixed number of them: a later change that
    # adds a second git invocation should have to pin it too, not fail here
    # for having added one. The assert above guarantees the list is non-empty.
    for call in calls:
        assert call["cwd"] == paths.REPO_ROOT, (
            f"{call['command']} ran with cwd={call['cwd']}, expected {paths.REPO_ROOT}"
        )


def test_get_commit_sha_prefers_the_baked_in_env_var(monkeypatch):
    """Docker bakes EMPIRE_COMMIT_SHA in at build time and has no .git."""
    monkeypatch.setenv("EMPIRE_COMMIT_SHA", "abc1234")
    monkeypatch.setattr(paths, "is_git_checkout", lambda: False)

    assert server.get_commit_sha() == "abc1234"


def test_run_derives_ssl_kwargs_from_cert_util_constants(monkeypatch, tmp_path):
    """A rename of CERT_FILENAME/KEY_FILENAME must not desync uvicorn's ssl
    kwargs from what generate_self_signed_cert actually writes -- re-hardcoding
    the two filename strings here would otherwise pass unnoticed.

    Doubles as the boot-path assertion that a package install shells out to git
    nowhere in run(). Removing the submodule helpers left get_commit_sha as the
    only git caller, so a test naming that one function no longer covers the
    module; driving run() end to end does, and keeps covering it if another
    caller is added.
    """
    monkeypatch.setattr(paths, "is_git_checkout", lambda: False)
    monkeypatch.delenv("EMPIRE_COMMIT_SHA", raising=False)

    def _explode(*args, **kwargs):
        raise AssertionError(f"git must not run on a package install: {args}")

    _stub_subprocess(monkeypatch, _explode)
    # Not part of the branch under test, but setup_logging() attaches handlers
    # to the root logger for the life of the process -- skip it so this test
    # doesn't leak logging state into the rest of the session.
    monkeypatch.setattr(server, "setup_logging", lambda args: None)
    monkeypatch.setattr(server.config_manager, "CERT_DIR", tmp_path / "cert")
    monkeypatch.setattr(server.empire_config.api, "secure", True)

    generate_calls = []

    def _fake_generate(cert_dir):
        generate_calls.append(cert_dir)
        return (
            cert_dir / server.cert_util.CERT_FILENAME,
            cert_dir / server.cert_util.KEY_FILENAME,
        )

    monkeypatch.setattr(server.cert_util, "generate_self_signed_cert", _fake_generate)

    uvicorn_calls = []
    monkeypatch.setattr(
        server.uvicorn, "run", lambda *a, **kwargs: uvicorn_calls.append(kwargs)
    )

    args = SimpleNamespace(version=False, reset=False, clean=False, log_level=None)

    # run() installs a real SIGINT handler; restore whatever was there before
    # so this test doesn't change process-wide signal disposition.
    original_sigint = signal.getsignal(signal.SIGINT)
    try:
        with pytest.raises(SystemExit):
            server.run(args)
    finally:
        signal.signal(signal.SIGINT, original_sigint)

    cert_path = tmp_path / "cert"
    assert generate_calls == [cert_path]

    kwargs = uvicorn_calls[0]
    assert kwargs["ssl_keyfile"] == str(cert_path / server.cert_util.KEY_FILENAME)
    assert kwargs["ssl_certfile"] == str(cert_path / server.cert_util.CERT_FILENAME)
