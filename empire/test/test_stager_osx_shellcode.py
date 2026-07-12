"""Generation tests for the osx/shellcode stager (setuid+execve shellcode with
an appended launcher, per architecture).
"""

import pytest

from empire.server.core.exceptions import StagerGenerationException
from empire.server.stagers.osx.shellcode import Stager as OsxShellcodeModule

LISTENER = "new-listener-1"


def _stager(main, **options):
    stager = OsxShellcodeModule(main)
    stager.options["Listener"]["Value"] = LISTENER
    for key, value in options.items():
        stager.options[key]["Value"] = value
    return stager


def test_osx_shellcode_x64(main):
    result = _stager(main).generate()

    assert result.startswith("\x48\x31\xff")  # xor rdi, rdi (x64 setuid)
    assert result.endswith("\x00")
    assert len(result) > 60  # noqa: PLR2004  (shellcode + embedded launcher)


def test_osx_shellcode_x86(main):
    result = _stager(main, Architecture="x86").generate()

    assert result.startswith("\x31\xdb")  # xor ebx, ebx (x86 setuid)
    assert result.endswith("\x00")


def test_osx_shellcode_invalid_listener_raises(main):
    stager = OsxShellcodeModule(main)
    stager.options["Listener"]["Value"] = "not-a-listener"
    with pytest.raises(StagerGenerationException, match="Invalid listener"):
        stager.generate()


def test_osx_shellcode_empty_launcher_raises(main, monkeypatch):
    monkeypatch.setattr(main.stagergenv2, "generate_launcher", lambda *a, **k: "")
    with pytest.raises(StagerGenerationException, match="Error in launcher"):
        _stager(main).generate()
