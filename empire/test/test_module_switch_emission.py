"""Regression tests for issue #1518.

`custom_generate` PowerShell modules hand-roll a ``for option, raw_value in
params.items()`` loop to build their command string. The canonical
``powershell_template.py`` they were copied from emitted ``-Option Value`` for
any non-``"true"`` value, with no skip for a native-``False`` boolean -- so an
unset ``[switch]`` option was emitted as the literal ``-Option False`` (a stray
positional / unintended switch value that misbehaves on the agent).

These tests drive each fixed module's real ``generate()`` with a native-bool
option set ``False`` and assert the malformed ``-Option False`` text is absent,
that a ``True`` switch still emits a bare flag, and that ordinary value options
pass through unchanged. Native-bool coercion itself is covered by
``test_module_service.test_execute_module_custom_generate_native_bool_gates_branch``.
"""

import base64
import re
from pathlib import Path
from unittest.mock import Mock

import pytest

from empire.server.core.module_service import ModuleService
from empire.server.modules.powershell_template import Module as PowershellTemplateModule


@pytest.fixture(scope="module")
def main_menu_mock(models, install_path):
    main_menu = Mock()
    main_menu.install_path = Path(install_path)
    main_menu.obfuscationv2 = Mock()
    main_menu.obfuscationv2.get_obfuscation_config = Mock(
        return_value=models.ObfuscationConfig(
            language="powershell", command="", enabled=False
        )
    )
    main_menu.obfuscationv2.obfuscate_keywords = Mock(side_effect=lambda x: x)

    # deaduser builds a launcher via a stager template and requires an active
    # listener. Stub both so its generate() reaches the option-emit loop.
    main_menu.listenersv2.get_active_listener_by_name = Mock(return_value=Mock())
    stager = Mock()
    stager.options = {"Listener": {"Value": ""}, "Base64": {"Value": True}}
    stager.generate = Mock(return_value="LAUNCHER_CODE")
    main_menu.stagertemplatesv2.new_instance = Mock(return_value=stager)

    return main_menu


@pytest.fixture(scope="module")
def module_service(main_menu_mock):
    module_service = ModuleService(main_menu=main_menu_mock)
    # custom_generate modules reach finalize_module / get_module_source via this.
    main_menu_mock.modulesv2 = module_service
    return module_service


@pytest.fixture
def obf_disabled(models):
    return models.ObfuscationConfig(language="powershell", command="", enabled=False)


def _generate(module_service, obf_disabled, module_id, params):
    """Run a real shipped module's generate() and return the finalized script."""
    module = module_service.modules[module_id]
    result = module_service._generate_script(
        None, module, params, "powershell", obf_disabled
    )
    # Every module under test is custom_generate and returns the finalized
    # script string directly.
    assert isinstance(result, str)
    return result


def test_find_fruit_unset_switch_not_emitted(module_service, obf_disabled):
    module_id = "powershell_situational_awareness_host_find_fruit"
    base = {
        "Agent": "ABC",
        "ShowAll": False,
        "Rhosts": "10.0.0.0/24",
        "Port": "",
        "Path": "",
        "Timeout": "50",
        "Threads": "10",
        "FoundOnly": True,
        "OutputFunction": "Out-String",
    }

    script = _generate(
        module_service, obf_disabled, module_id, {**base, "UseSSL": False}
    )
    assert "-UseSSL" not in script  # never "-UseSSL False"
    # value options pass through unchanged
    assert "-Rhosts 10.0.0.0/24" in script
    assert "-Timeout 50" in script
    # a True default switch still emits a bare flag
    assert "-FoundOnly" in script
    assert "-FoundOnly True" not in script

    script = _generate(
        module_service, obf_disabled, module_id, {**base, "UseSSL": True}
    )
    assert "-UseSSL" in script
    assert "-UseSSL True" not in script


def test_wiretap_unset_switch_not_emitted(module_service, obf_disabled):
    module_id = "powershell_situational_awareness_host_wiretap"
    base = {
        "Agent": "ABC",
        "record_mic": True,
        "record_sys": False,
        "record_audio": "10",
        "capture_screen": True,
        "capture_webcam": False,
        "keylogger": True,
        "listen_for_passwords": False,
        "time": "10s",
    }

    script = _generate(module_service, obf_disabled, module_id, base)
    # WireTap emits switches with no leading dash, so a False switch leaked as
    # e.g. "record_sys False".
    for switch in ("record_sys", "capture_webcam", "listen_for_passwords"):
        assert f"{switch} False" not in script
    # set switches are emitted bare (no dash, no value) ...
    for switch in ("record_mic", "capture_screen", "keylogger"):
        assert switch in script
        assert f"{switch} True" not in script
    # ... and each must be a space-separated token, never glued onto the
    # preceding value option. record_audio emits "record_audio 10", and a
    # switch appended with no separator produced "10keylogger" -- garbage once
    # Invoke-WireTap tokenizes -Command on spaces, silently dropping the switch.
    command = re.findall(r'Invoke-WireTap -Command "([^"]*)"', script)[-1]
    tokens = command.split(" ")
    for switch in ("record_mic", "capture_screen", "keylogger"):
        assert switch in tokens, f"{switch!r} not a standalone token in {command!r}"
    # value option + the special-cased time option pass through
    assert "record_audio 10" in script
    assert " 10s" in script


def test_runas_unset_switch_not_emitted(module_service, obf_disabled):
    module_id = "powershell_management_runas"
    base = {
        "Agent": "ABC",
        "CredID": "",
        "Domain": "CORP",
        "UserName": "bob",
        "Password": "pw",
        "Cmd": "calc.exe",
        "Arguments": "",
    }

    script = _generate(
        module_service, obf_disabled, module_id, {**base, "ShowWindow": False}
    )
    assert "-ShowWindow" not in script  # never "-ShowWindow 'False'"
    # value options keep runas' single-quoted format
    assert "-UserName 'bob'" in script
    assert "-Cmd 'calc.exe'" in script

    script = _generate(
        module_service, obf_disabled, module_id, {**base, "ShowWindow": True}
    )
    assert "-ShowWindow" in script
    assert "-ShowWindow 'True'" not in script


def test_inveigh_relay_unset_switch_not_emitted(module_service, obf_disabled):
    module_id = "powershell_lateral_movement_inveigh_relay"
    # A non-empty Command bypasses the listener/launcher path.
    base = {
        "Agent": "ABC",
        "Listener": "",
        "UserAgent": "default",
        "Proxy_": "default",
        "ProxyCreds": "default",
        "Command": "whoami",
        "ObfuscateCommand": "Token\\All\\1",
    }

    script = _generate(
        module_service,
        obf_disabled,
        module_id,
        {**base, "Obfuscate": False, "SMB1": False},
    )
    assert '-Obfuscate "False"' not in script
    assert '-SMB1 "False"' not in script
    # value option keeps inveigh's double-quoted format
    assert '-ObfuscateCommand "Token\\All\\1"' in script

    script = _generate(
        module_service,
        obf_disabled,
        module_id,
        {**base, "Obfuscate": False, "SMB1": True},
    )
    assert "-SMB1" in script
    assert '-SMB1 "True"' not in script


def test_get_subnet_ranges_ips_not_emitted(module_service, obf_disabled):
    module_id = "powershell_situational_awareness_network_powerview_get_subnet_ranges"
    base = {"Agent": "ABC", "Domain": "", "OutputFunction": "Out-String"}

    # IPs is consumed separately (list_computers) and must never be re-emitted
    # into the standalone pipeline as a CLI switch.
    script = _generate(module_service, obf_disabled, module_id, {**base, "IPs": False})
    assert "-IPs" not in script
    assert "$Servers;" not in script  # IPs False -> individual IPs not listed

    script = _generate(module_service, obf_disabled, module_id, {**base, "IPs": True})
    assert "-IPs" not in script
    assert "$Servers;" in script  # IPs True -> individual IPs listed


def _decode_enc_launcher(script):
    """Pull the base64 from a powershell.exe -enc launcher and decode it."""
    match = re.search(r"-enc\s+([A-Za-z0-9+/=]+)", script)
    assert match, f"no -enc payload found in: {script!r}"
    return base64.b64decode(match.group(1)).decode("utf-16-le")


def test_deaduser_unset_switch_not_emitted(module_service, obf_disabled):
    module_id = "powershell_persistence_powerbreach_deaduser"
    base = {
        "Agent": "ABC",
        "Listener": "http",
        "OutFile": "",
        "Timeout": "0",
        "Sleep": "30",
        "Username": "bob",
    }

    script = _generate(
        module_service, obf_disabled, module_id, {**base, "Domain": False}
    )
    decoded = _decode_enc_launcher(script)
    assert "-Domain" not in decoded  # never "-Domain False"
    assert "-Username bob" in decoded  # value option preserved

    script = _generate(
        module_service, obf_disabled, module_id, {**base, "Domain": True}
    )
    decoded = _decode_enc_launcher(script)
    assert "-Domain" in decoded
    assert "-Domain True" not in decoded


def test_powershell_template_unset_switch_not_emitted():
    """The template every custom_generate module is copied from must not seed
    the ``-Option False`` bug into new modules."""
    main_menu = Mock()
    main_menu.modulesv2.get_module_source = Mock(return_value=("SCRIPT_BODY", None))
    main_menu.modulesv2.finalize_module = Mock(
        side_effect=lambda script, script_end, **kwargs: script + script_end
    )
    module = Mock()
    module.script_path = "fake/path.ps1"

    params = {"Agent": "ABC", "MySwitch": False, "MyValue": "keepme"}
    script = PowershellTemplateModule.generate(main_menu, module, params, False, "")
    assert "-MySwitch" not in script  # never "-MySwitch False"
    assert "-MyValue keepme" in script

    params = {"Agent": "ABC", "MySwitch": True, "MyValue": "keepme"}
    script = PowershellTemplateModule.generate(main_menu, module, params, False, "")
    assert "-MySwitch" in script
    assert "-MySwitch True" not in script
