"""Generation tests for a cluster of windows stagers: wmic (XSL), launcher_vbs,
war (JSP/zip), hta, and cmd_exec (msfvenom-wrapped). All embed a powershell
launcher into a device/format-specific payload.
"""

import io
import zipfile

import pytest

from empire.server.core.exceptions import StagerGenerationException
from empire.server.stagers.windows import cmd_exec
from empire.server.stagers.windows.cmd_exec import Stager as CmdExecStager
from empire.server.stagers.windows.hta import Stager as HtaStager
from empire.server.stagers.windows.launcher_vbs import Stager as LauncherVbsStager
from empire.server.stagers.windows.war import Stager as WarStager
from empire.server.stagers.windows.wmic import Stager as WmicStager

LISTENER = "new-listener-1"


# --------------------------------------------------------------------------- #
# wmic (XSL stylesheet)
# --------------------------------------------------------------------------- #
def test_wmic_powershell_builds_xsl(main):
    stager = WmicStager(main)
    stager.options["Listener"]["Value"] = LISTENER

    code = stager.generate()

    assert code.startswith('<?xml version="1.0"?>')
    assert "XSL/Transform" in code
    assert 'ActiveXObject("WScript.Shell").Run(' in code
    assert "-enc" in code
    assert code.endswith("</ms:script></stylesheet>")


def test_wmic_empty_launcher_raises(main, monkeypatch):
    monkeypatch.setattr(main.stagergenv2, "generate_launcher", lambda *a, **k: "")
    stager = WmicStager(main)
    stager.options["Listener"]["Value"] = LISTENER
    with pytest.raises(StagerGenerationException):
        stager.generate()


# --------------------------------------------------------------------------- #
# launcher_vbs
# --------------------------------------------------------------------------- #
def test_launcher_vbs_builds_vbs(main):
    stager = LauncherVbsStager(main)
    stager.options["Listener"]["Value"] = LISTENER

    code = stager.generate()

    assert 'WScript.CreateObject("WScript.Shell")' in code
    assert "objShell.Run command,0" in code
    assert "-enc" in code


def test_launcher_vbs_empty_launcher_raises(main, monkeypatch):
    monkeypatch.setattr(main.stagergenv2, "generate_launcher", lambda *a, **k: "")
    stager = LauncherVbsStager(main)
    stager.options["Listener"]["Value"] = LISTENER
    with pytest.raises(StagerGenerationException):
        stager.generate()


# --------------------------------------------------------------------------- #
# war (JSP packaged in a zip)
# --------------------------------------------------------------------------- #
def test_war_packages_jsp_with_launcher(main):
    stager = WarStager(main)
    stager.options["Listener"]["Value"] = LISTENER
    stager.options["AppName"]["Value"] = "myapp"

    result = stager.generate()

    zf = zipfile.ZipFile(io.BytesIO(result))
    jsp = zf.read("myapp.jsp").decode()
    web_xml = zf.read("WEB-INF/web.xml").decode()

    assert "Runtime.getRuntime().exec(" in jsp
    assert "-enc" in jsp
    assert "<servlet-name>myapp</servlet-name>" in web_xml


def test_war_app_name_defaults_to_listener(main):
    stager = WarStager(main)
    stager.options["Listener"]["Value"] = LISTENER
    stager.options["AppName"]["Value"] = ""

    result = stager.generate()

    zf = zipfile.ZipFile(io.BytesIO(result))
    assert f"{LISTENER}.jsp" in zf.namelist()


def test_war_empty_launcher_raises(main, monkeypatch):
    monkeypatch.setattr(main.stagergenv2, "generate_launcher", lambda *a, **k: "")
    stager = WarStager(main)
    stager.options["Listener"]["Value"] = LISTENER
    with pytest.raises(StagerGenerationException):
        stager.generate()


# --------------------------------------------------------------------------- #
# hta
# --------------------------------------------------------------------------- #
def test_hta_builds_html(main):
    stager = HtaStager(main)
    stager.options["Listener"]["Value"] = LISTENER

    code = stager.generate()

    assert code.startswith("<html><head><script>")
    assert "new ActiveXObject('WScript.Shell').Run(c)" in code
    assert "-enc" in code


def test_hta_empty_launcher_raises(main, monkeypatch):
    monkeypatch.setattr(main.stagergenv2, "generate_launcher", lambda *a, **k: "")
    stager = HtaStager(main)
    stager.options["Listener"]["Value"] = LISTENER
    with pytest.raises(StagerGenerationException):
        stager.generate()


# --------------------------------------------------------------------------- #
# cmd_exec (msfvenom-wrapped; subprocess stubbed)
# --------------------------------------------------------------------------- #
def test_cmd_exec_x64_builds_msfvenom_command(main, monkeypatch):
    captured = {}

    def fake_check_output(command, **kwargs):
        captured["command"] = command
        return b"SHELLCODE-BYTES"

    monkeypatch.setattr(cmd_exec.subprocess, "check_output", fake_check_output)

    stager = CmdExecStager(main)
    stager.options["Listener"]["Value"] = LISTENER
    stager.options["Arch"]["Value"] = "x64"
    stager.options["MSF_Format"]["Value"] = "exe"

    result = stager.generate()

    assert result == b"SHELLCODE-BYTES"
    assert "msfvenom -p windows/x64/exec" in captured["command"]
    assert "-f exe" in captured["command"]


def test_cmd_exec_x86_payload(main, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        cmd_exec.subprocess,
        "check_output",
        lambda command, **k: captured.setdefault("command", command) or b"SC",
    )

    stager = CmdExecStager(main)
    stager.options["Listener"]["Value"] = LISTENER
    stager.options["Arch"]["Value"] = "x86"

    stager.generate()

    assert "msfvenom -p windows/exec" in captured["command"]


def test_cmd_exec_empty_launcher_raises(main, monkeypatch):
    monkeypatch.setattr(main.stagergenv2, "generate_launcher", lambda *a, **k: "")
    stager = CmdExecStager(main)
    stager.options["Listener"]["Value"] = LISTENER
    with pytest.raises(StagerGenerationException):
        stager.generate()
