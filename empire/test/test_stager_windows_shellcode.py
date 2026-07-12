"""Generation tests for the windows/shellcode stager. The shellcode backends
(generate_powershell_shellcode / generate_python_shellcode / donut) are env-
gated, so they're stubbed to cover the language dispatch and guards.
"""

import pytest

from empire.server.core.exceptions import StagerGenerationException
from empire.server.stagers.windows import shellcode as shellcode_mod
from empire.server.stagers.windows.shellcode import Stager as ShellcodeStager

LISTENER = "new-listener-1"


def _stager(main, **options):
    stager = ShellcodeStager(main)
    stager.options["Listener"]["Value"] = LISTENER
    for key, value in options.items():
        stager.options[key]["Value"] = value
    return stager


def test_shellcode_invalid_listener_raises(main):
    stager = ShellcodeStager(main)
    stager.options["Listener"]["Value"] = "not-a-listener"
    with pytest.raises(StagerGenerationException, match="Invalid listener"):
        stager.generate()


def test_shellcode_empty_launcher_raises(main, monkeypatch):
    monkeypatch.setattr(main.stagergenv2, "generate_launcher", lambda *a, **k: "")
    with pytest.raises(StagerGenerationException, match="Error in launcher"):
        _stager(main).generate()


def test_shellcode_failed_launcher_raises(main, monkeypatch):
    monkeypatch.setattr(main.stagergenv2, "generate_launcher", lambda *a, **k: "failed")
    with pytest.raises(StagerGenerationException, match="Error in launcher"):
        _stager(main).generate()


def test_shellcode_powershell_returns_shellcode(main, monkeypatch):
    monkeypatch.setattr(
        main.stagergenv2,
        "generate_powershell_shellcode",
        lambda *a, **k: (b"PS-SHELLCODE", None),
    )
    result = _stager(main, Language="powershell").generate()
    assert result == b"PS-SHELLCODE"


def test_shellcode_powershell_backend_error_raises(main, monkeypatch):
    monkeypatch.setattr(
        main.stagergenv2,
        "generate_powershell_shellcode",
        lambda *a, **k: (None, "backend unavailable"),
    )
    with pytest.raises(StagerGenerationException, match="backend unavailable"):
        _stager(main, Language="powershell").generate()


def test_shellcode_python_returns_shellcode(main, monkeypatch):
    monkeypatch.setattr(
        main.stagergenv2,
        "generate_python_shellcode",
        lambda *a, **k: (b"PY-SHELLCODE", None),
    )
    result = _stager(main, Language="python").generate()
    assert result == b"PY-SHELLCODE"


def test_shellcode_python_backend_error_raises(main, monkeypatch):
    monkeypatch.setattr(
        main.stagergenv2,
        "generate_python_shellcode",
        lambda *a, **k: (None, "python backend down"),
    )
    with pytest.raises(StagerGenerationException, match="python backend down"):
        _stager(main, Language="python").generate()


@pytest.mark.parametrize("arch", ["x86", "x64", "both"])
def test_shellcode_csharp_without_donut_raises(main, monkeypatch, arch):
    # arch_type is resolved (x86->1, x64->2, both->3) before the donut check.
    monkeypatch.setattr(shellcode_mod, "donut", None)
    with pytest.raises(
        StagerGenerationException, match="donut-shellcode not installed"
    ):
        _stager(main, Language="csharp", Architecture=arch).generate()


def test_shellcode_invalid_language_raises(main, monkeypatch):
    # Direct generate() bypasses the strict-option validation.
    monkeypatch.setattr(
        main.stagergenv2, "generate_launcher", lambda *a, **k: "some-launcher"
    )
    stager = _stager(main)
    stager.options["Language"]["Value"] = "ruby"
    with pytest.raises(StagerGenerationException, match="Invalid launcher language"):
        stager.generate()
