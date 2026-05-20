import contextlib
import subprocess
from pathlib import Path

import pytest

from empire.server.core.exceptions import ModuleExecutionException
from empire.server.core.go import GoCompiler


def test_go_compiler_jinja_env_path(tmp_path):
    """Test that GoCompiler correctly constructs the jinja_env loader path."""
    # Create the expected directory structure
    gopire_dir = tmp_path / "data" / "agent" / "gopire"
    gopire_dir.mkdir(parents=True)

    compiler = GoCompiler(install_path=tmp_path)

    assert compiler.install_path == tmp_path

    loader = compiler.jinja_env.loader
    assert str(gopire_dir) in loader.searchpath


def test_go_compiler_accepts_path_object():
    """Test that GoCompiler works with a Path object as install_path."""
    install = Path("/fake/install/path")
    compiler = GoCompiler(install_path=install)

    assert compiler.install_path == install
    expected_loader_path = str(install / "data/agent/gopire")
    assert expected_loader_path in compiler.jinja_env.loader.searchpath


def _seed_gopire(install_path: Path) -> Path:
    """Create a minimal gopire src tree so compile_stager can copytree it."""
    gopire_dir = install_path / "data" / "agent" / "gopire"
    gopire_dir.mkdir(parents=True)
    (gopire_dir / "main.template").write_text("package main\nfunc main() {}\n")
    (gopire_dir / "go.mod").write_text("module gopire\n")
    return gopire_dir


@pytest.mark.parametrize(
    ("returncode", "stdout", "stderr", "expected_substrings"),
    [
        # Signal kill (OOM, AV, cgroup) — empty stderr is the diagnostic
        # gap Anthony hit. Message must include returncode + signal hint.
        (-9, "", "", ["rc=-9", "no output", "likely killed by signal"]),
        # Real go-build error written to stderr.
        (1, "", "main.go:1: syntax error", ["rc=1", "main.go:1: syntax error"]),
        # Pathological: stderr empty but stdout has the error.
        (2, "module download failed", "", ["rc=2", "module download failed"]),
    ],
    ids=["signal_kill_empty_streams", "stderr_has_error", "stdout_fallback"],
)
def test_compile_stager_includes_diagnostics_when_go_build_fails(
    tmp_path, monkeypatch, returncode, stdout, stderr, expected_substrings
):
    """Anthony's bug: rc != 0 + empty stderr was rendered as `Go build failed: `
    (two spaces, no info). New message must include returncode and fall back
    through stderr -> stdout -> signal-kill hint."""
    _seed_gopire(tmp_path)
    compiler = GoCompiler(install_path=tmp_path)

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["go", "build"],
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )

    monkeypatch.setattr("empire.server.core.go.subprocess.run", fake_run)

    with pytest.raises(ModuleExecutionException) as excinfo:
        compiler.compile_stager(template_vars={}, task_name="stager")

    message = str(excinfo.value)
    for substring in expected_substrings:
        assert substring in message, (
            f"expected {substring!r} in error message, got: {message!r}"
        )
    # The preservation note should still land regardless of the failure shape.
    assert "preserved at" in message or "failed to preserve" in message


def test_compile_stager_explicit_goos_wins_over_operator_env(tmp_path, monkeypatch):
    """Cache-poisoning vector: prior code did `env={**env, **os.environ}` so an
    operator-set `GOOS=linux` silently overrode a function-arg `goos="windows"`
    cross-compile. The fix swaps the merge order; this test pins it."""
    _seed_gopire(tmp_path)
    compiler = GoCompiler(install_path=tmp_path)

    monkeypatch.setenv("GOOS", "linux")
    monkeypatch.setenv("GOARCH", "386")

    captured: dict = {}

    def fake_run(*args, **kwargs):
        captured["env"] = kwargs.get("env", {})
        # Return success so the function returns normally.
        # We don't care about the output path for this test — capture and exit.
        return subprocess.CompletedProcess(
            args=args[0] if args else [],
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr("empire.server.core.go.subprocess.run", fake_run)
    # shutil.move at the tail of compile_stager will fail because fake_run
    # didn't actually produce the binary; bail out at that point — we only
    # care about the env that reached subprocess.run.
    with contextlib.suppress(FileNotFoundError, OSError):
        compiler.compile_stager(
            template_vars={}, task_name="stager", goos="windows", goarch="amd64"
        )

    assert captured["env"]["GOOS"] == "windows", (
        f"function arg should win, got GOOS={captured['env'].get('GOOS')!r}"
    )
    assert captured["env"]["GOARCH"] == "amd64", (
        f"function arg should win, got GOARCH={captured['env'].get('GOARCH')!r}"
    )
