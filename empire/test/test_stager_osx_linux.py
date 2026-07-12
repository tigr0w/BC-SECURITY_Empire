"""Generation tests for the osx/application, osx/dylib, and linux/bash stagers.

osx/application and osx/dylib delegate the final packaging to
generate_appbundle / generate_dylib (env-gated toolchain); those are stubbed so
the tests cover the launcher preprocessing and guards. linux/bash is a pure
text generator.
"""

import pytest

from empire.server.core.exceptions import StagerGenerationException
from empire.server.stagers.linux.bash import Stager as LinuxBashStager
from empire.server.stagers.osx.application import Stager as OsxAppStager
from empire.server.stagers.osx.dylib import Stager as OsxDylibStager

LISTENER = "new-listener-1"


# --------------------------------------------------------------------------- #
# linux/bash
# --------------------------------------------------------------------------- #
def test_linux_bash_builds_self_deleting_script(main):
    stager = LinuxBashStager(main)
    stager.options["Listener"]["Value"] = LISTENER

    code = stager.generate()

    assert code.startswith("#!/bin/bash\n")
    assert 'rm -f "$0"' in code
    assert code.endswith("exit\n")
    # A python launcher is embedded between the shebang and the self-delete.
    assert len(code.splitlines()) >= 4  # noqa: PLR2004


def test_linux_bash_empty_launcher_raises(main, monkeypatch):
    monkeypatch.setattr(main.stagergenv2, "generate_launcher", lambda *a, **k: "")
    stager = LinuxBashStager(main)
    stager.options["Listener"]["Value"] = LISTENER
    with pytest.raises(StagerGenerationException):
        stager.generate()


# --------------------------------------------------------------------------- #
# osx/application
# --------------------------------------------------------------------------- #
def test_osx_application_preprocesses_launcher_and_packages(main, monkeypatch):
    captured = {}

    def fake_appbundle(**kwargs):
        captured.update(kwargs)
        return b"APP-BUNDLE-ZIP"

    monkeypatch.setattr(main.stagergenv2, "generate_appbundle", fake_appbundle)

    stager = OsxAppStager(main)
    stager.options["Listener"]["Value"] = LISTENER
    stager.options["Architecture"]["Value"] = "x64"

    result = stager.generate()

    assert result == b"APP-BUNDLE-ZIP"
    # The python "echo ... | python3 &" wrapper is stripped before packaging.
    assert captured["launcher_code"]
    assert "echo " not in captured["launcher_code"]
    assert "| python3 &" not in captured["launcher_code"]
    assert captured["arch"] == "x64"


def test_osx_application_empty_launcher_raises(main, monkeypatch):
    monkeypatch.setattr(main.stagergenv2, "generate_launcher", lambda *a, **k: "")
    stager = OsxAppStager(main)
    stager.options["Listener"]["Value"] = LISTENER
    with pytest.raises(StagerGenerationException):
        stager.generate()


# --------------------------------------------------------------------------- #
# osx/dylib
# --------------------------------------------------------------------------- #
def test_osx_dylib_preprocesses_launcher_and_builds(main, monkeypatch):
    captured = {}

    def fake_dylib(**kwargs):
        captured.update(kwargs)
        return b"DYLIB-BYTES"

    monkeypatch.setattr(main.stagergenv2, "generate_dylib", fake_dylib)

    stager = OsxDylibStager(main)
    stager.options["Listener"]["Value"] = LISTENER
    stager.options["Architecture"]["Value"] = "x64"
    stager.options["Hijacker"]["Value"] = False

    result = stager.generate()

    assert result == b"DYLIB-BYTES"
    assert captured["arch"] == "x64"
    assert "echo " not in captured["launcher_code"]


def test_osx_dylib_missing_arch_raises(main):
    stager = OsxDylibStager(main)
    stager.options["Listener"]["Value"] = LISTENER
    stager.options["Architecture"]["Value"] = ""
    with pytest.raises(StagerGenerationException, match="valid architecture"):
        stager.generate()


def test_osx_dylib_empty_launcher_raises(main, monkeypatch):
    monkeypatch.setattr(main.stagergenv2, "generate_launcher", lambda *a, **k: "")
    stager = OsxDylibStager(main)
    stager.options["Listener"]["Value"] = LISTENER
    stager.options["Architecture"]["Value"] = "x64"
    with pytest.raises(StagerGenerationException):
        stager.generate()
