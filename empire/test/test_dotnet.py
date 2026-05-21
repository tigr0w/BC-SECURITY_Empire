import subprocess

import pytest

from empire.server.core.dotnet import DotnetCompiler
from empire.server.core.exceptions import ModuleExecutionException


@pytest.fixture
def compiler(tmp_path, monkeypatch):
    """A DotnetCompiler that doesn't actually try to sync EmpireCompiler.

    `__init__` calls `sync_empire_compiler` which would fetch the binary;
    short-circuit it for unit tests by stubbing the function.
    """

    def fake_sync(*_args, **_kwargs):
        return tmp_path

    monkeypatch.setattr("empire.server.core.dotnet.sync_empire_compiler", fake_sync)
    return DotnetCompiler(install_path=tmp_path)


@pytest.mark.parametrize(
    ("returncode", "stdout", "stderr", "expected_substrings"),
    [
        (-9, "", "", ["rc=-9", "no output", "likely killed by signal"]),
        (1, "", "compiler error: foo", ["rc=1", "compiler error: foo"]),
        (2, "diagnostic on stdout", "", ["rc=2", "diagnostic on stdout"]),
    ],
    ids=["signal_kill_empty_streams", "stderr_has_error", "stdout_fallback"],
)
def test_compile_task_includes_diagnostics_when_empire_compiler_fails(
    compiler, monkeypatch, returncode, stdout, stderr, expected_substrings
):
    """Symmetric to the go.py fix: rc != 0 with empty stderr previously
    rendered as `EmpireCompiler execution failed with error: ` (no info).
    New message must include returncode + stdout fallback."""

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["./EmpireCompiler"],
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )

    monkeypatch.setattr("empire.server.core.dotnet.subprocess.run", fake_run)

    with pytest.raises(ModuleExecutionException) as excinfo:
        compiler.compile_task(compiler_yaml="dummy: yaml", task_name="task")

    message = str(excinfo.value)
    for substring in expected_substrings:
        assert substring in message, (
            f"expected {substring!r} in error message, got: {message!r}"
        )


@pytest.mark.parametrize(
    ("returncode", "stdout", "stderr", "expected_substrings"),
    [
        (-9, "", "", ["rc=-9", "no output", "likely killed by signal"]),
        (1, "", "compiler error: bar", ["rc=1", "compiler error: bar"]),
        (2, "diagnostic on stdout", "", ["rc=2", "diagnostic on stdout"]),
    ],
    ids=["signal_kill_empty_streams", "stderr_has_error", "stdout_fallback"],
)
def test_compile_stager_includes_diagnostics_when_empire_compiler_fails(
    compiler, monkeypatch, returncode, stdout, stderr, expected_substrings
):
    """Same shape as compile_task — pin the diagnostic for the stager path."""

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["./EmpireCompiler"],
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )

    monkeypatch.setattr("empire.server.core.dotnet.subprocess.run", fake_run)

    with pytest.raises(ModuleExecutionException) as excinfo:
        compiler.compile_stager(compiler_yaml="dummy: yaml", task_name="stager")

    message = str(excinfo.value)
    for substring in expected_substrings:
        assert substring in message, (
            f"expected {substring!r} in error message, got: {message!r}"
        )
