"""Unit tests for empire.server.utils.file_util.

``ensure_user_ownership`` (root-only recursive chown) and ``run_as_user``
(sudo-preserving subprocess wrapper) were largely uncovered. These exercise
their branches with monkeypatched os/pwd/subprocess so no privileges are
needed.
"""

import os
import subprocess
from types import SimpleNamespace

import pytest

from empire.server.utils import file_util


# --------------------------------------------------------------------------- #
# ensure_user_ownership
# --------------------------------------------------------------------------- #
def _no_chown(monkeypatch):
    """Install an os.chown that fails the test if it is ever called."""
    calls = []

    def fake_chown(*a, **k):
        calls.append((a, k))

    monkeypatch.setattr(os, "chown", fake_chown)
    return calls


def test_ensure_ownership_noop_when_not_root(monkeypatch, tmp_path):
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    calls = _no_chown(monkeypatch)

    file_util.ensure_user_ownership(tmp_path, user="someone")

    assert calls == []


def test_ensure_ownership_noop_for_root_target(monkeypatch, tmp_path):
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    calls = _no_chown(monkeypatch)

    file_util.ensure_user_ownership(tmp_path, user="root")

    assert calls == []


def test_ensure_ownership_noop_when_no_sudo_user(monkeypatch, tmp_path):
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.delenv("SUDO_USER", raising=False)
    calls = _no_chown(monkeypatch)

    file_util.ensure_user_ownership(tmp_path)

    assert calls == []


def test_ensure_ownership_unknown_user_skips(monkeypatch, tmp_path):
    monkeypatch.setattr(os, "geteuid", lambda: 0)

    def raise_keyerror(_name):
        raise KeyError

    monkeypatch.setattr(file_util.pwd, "getpwnam", raise_keyerror)
    calls = _no_chown(monkeypatch)

    file_util.ensure_user_ownership(tmp_path, user="ghost")

    assert calls == []


def test_ensure_ownership_already_correct_is_noop(monkeypatch, tmp_path):
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    st = tmp_path.stat()
    monkeypatch.setattr(
        file_util.pwd,
        "getpwnam",
        lambda _n: SimpleNamespace(pw_uid=st.st_uid, pw_gid=st.st_gid),
    )
    calls = _no_chown(monkeypatch)

    file_util.ensure_user_ownership(tmp_path, user="me")

    assert calls == []


def test_ensure_ownership_chowns_tree(monkeypatch, tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "f.txt").write_text("x")

    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        file_util.pwd,
        "getpwnam",
        lambda _n: SimpleNamespace(pw_uid=424242, pw_gid=424242),
    )
    chowned = []
    monkeypatch.setattr(os, "chown", lambda p, *a, **k: chowned.append(str(p)))

    file_util.ensure_user_ownership(tmp_path, user="target")

    # Root path plus every walked entry got chowned.
    assert str(tmp_path) in chowned
    assert str(tmp_path / "sub") in chowned
    assert str(tmp_path / "sub" / "f.txt") in chowned


def test_ensure_ownership_missing_path_returns(monkeypatch, tmp_path):
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        file_util.pwd,
        "getpwnam",
        lambda _n: SimpleNamespace(pw_uid=424242, pw_gid=424242),
    )
    calls = _no_chown(monkeypatch)

    # stat() on a non-existent path raises FileNotFoundError -> early return.
    file_util.ensure_user_ownership(tmp_path / "does-not-exist", user="target")

    assert calls == []


def test_ensure_ownership_skips_vanished_entry(monkeypatch, tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "f.txt").write_text("x")

    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        file_util.pwd,
        "getpwnam",
        lambda _n: SimpleNamespace(pw_uid=424242, pw_gid=424242),
    )

    def chown(p, *a, **k):
        # Top-level succeeds; entries look like they vanished mid-walk.
        if str(p) != str(tmp_path):
            raise FileNotFoundError

    monkeypatch.setattr(os, "chown", chown)

    file_util.ensure_user_ownership(tmp_path, user="target")


def test_ensure_ownership_reraises_on_root_chown_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        file_util.pwd,
        "getpwnam",
        lambda _n: SimpleNamespace(pw_uid=424242, pw_gid=424242),
    )

    def deny(*a, **k):
        raise PermissionError("nope")

    monkeypatch.setattr(os, "chown", deny)

    with pytest.raises(PermissionError):
        file_util.ensure_user_ownership(tmp_path, user="target")


def test_ensure_ownership_continues_past_entry_failure(monkeypatch, tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "f.txt").write_text("x")

    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        file_util.pwd,
        "getpwnam",
        lambda _n: SimpleNamespace(pw_uid=424242, pw_gid=424242),
    )

    def chown(p, *a, **k):
        # Top-level chown succeeds; per-entry chowns raise but must not abort.
        if str(p) != str(tmp_path):
            raise OSError("entry busy")

    monkeypatch.setattr(os, "chown", chown)

    # Should complete without raising despite the per-entry failures.
    file_util.ensure_user_ownership(tmp_path, user="target")


# --------------------------------------------------------------------------- #
# run_as_user
# --------------------------------------------------------------------------- #
def _fake_run(monkeypatch, stdout="output", exc=None):
    recorded = {}

    def fake_run(cmd, **kwargs):
        recorded["cmd"] = cmd
        recorded["kwargs"] = kwargs
        if exc is not None:
            raise exc
        return SimpleNamespace(stdout=stdout)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return recorded


def test_run_as_user_root_skips_sudo(monkeypatch):
    recorded = _fake_run(monkeypatch)

    file_util.run_as_user(["echo", "hi"], user="root")

    assert recorded["cmd"] == ["echo", "hi"]


def test_run_as_user_named_user_prepends_sudo(monkeypatch):
    recorded = _fake_run(monkeypatch)

    file_util.run_as_user(["git", "status"], user="alice")

    assert recorded["cmd"] == ["sudo", "-E", "-u", "alice", "git", "status"]


def test_run_as_user_defaults_to_sudo_user_env(monkeypatch):
    monkeypatch.setenv("SUDO_USER", "bob")
    recorded = _fake_run(monkeypatch)

    file_util.run_as_user(["whoami"])

    assert recorded["cmd"] == ["sudo", "-E", "-u", "bob", "whoami"]


def test_run_as_user_no_sudo_user_runs_plain(monkeypatch):
    monkeypatch.delenv("SUDO_USER", raising=False)
    recorded = _fake_run(monkeypatch)

    file_util.run_as_user(["whoami"])

    assert recorded["cmd"] == ["whoami"]


def test_run_as_user_capture_output_returns_stripped_stdout(monkeypatch):
    _fake_run(monkeypatch, stdout="  hello \n")

    result = file_util.run_as_user(["echo"], user="root", capture_output=True)

    assert result == "hello"


def test_run_as_user_without_capture_returns_none(monkeypatch):
    _fake_run(monkeypatch)

    result = file_util.run_as_user(["echo"], user="root")

    assert result is None


def test_run_as_user_reraises_called_process_error(monkeypatch):
    err = subprocess.CalledProcessError(
        1, ["boom"], output="out-data", stderr="err-data"
    )
    _fake_run(monkeypatch, exc=err)

    with pytest.raises(subprocess.CalledProcessError):
        file_util.run_as_user(["boom"], user="root")
