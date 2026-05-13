import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock

import yaml

from empire.server.core.bypass_service import BypassService
from empire.server.core.db import models
from empire.server.core.listener_template_service import ListenerTemplateService
from empire.server.core.profile_service import ProfileService
from empire.server.core.stager_template_service import StagerTemplateService
from empire.server.utils.data_util import ps_convert_to_oneliner
from empire.test.conftest import SERVER_CONFIG_LOC


def test_bypass_loader(monkeypatch):
    sys.argv = ["", "server", "--config", SERVER_CONFIG_LOC]
    session_mock = MagicMock()
    monkeypatch.setattr("empire.server.core.bypass_service.SessionLocal", session_mock)

    session_mock.begin.return_value.__enter__.return_value.query.return_value.first.return_value.install_path = "empire/server"

    session_mock.begin.return_value.__enter__.return_value.query.return_value.filter.return_value.first.return_value = None

    main_menu = Mock()
    main_menu.installPath = "empire/server"
    main_menu.install_path = Path("empire/server")

    BypassService(main_menu)

    min_call_count = 4
    assert (
        session_mock.begin.return_value.__enter__.return_value.add.call_count
        > min_call_count
    )


def test_bypass_loader_skips_oneliner_for_non_powershell(monkeypatch):
    """ps_convert_to_oneliner strips newlines, which would corrupt multi-line
    Python bypass scripts. The loader must only apply it to powershell bypasses."""
    sys.argv = ["", "server", "--config", SERVER_CONFIG_LOC]
    session_mock = MagicMock()
    monkeypatch.setattr("empire.server.core.bypass_service.SessionLocal", session_mock)

    session_mock.begin.return_value.__enter__.return_value.query.return_value.first.return_value.install_path = "empire/server"
    session_mock.begin.return_value.__enter__.return_value.query.return_value.filter.return_value.first.return_value = None

    main_menu = Mock()
    main_menu.installPath = "empire/server"
    main_menu.install_path = Path("empire/server")

    BypassService(main_menu)

    add_calls = (
        session_mock.begin.return_value.__enter__.return_value.add.call_args_list
    )
    loaded_bypasses = [
        call.args[0]
        for call in add_calls
        if call.args and isinstance(call.args[0], models.Bypass)
    ]
    bypasses_by_name = {b.name: b for b in loaded_bypasses}

    python_yaml = yaml.safe_load(
        Path("empire/server/bypasses/SafeChecksPython.yaml").read_text()
    )
    safechecks_python = bypasses_by_name.get("SafeChecksPython")
    assert safechecks_python is not None, "SafeChecksPython bypass was not loaded"
    assert safechecks_python.language == "python"
    assert safechecks_python.code == python_yaml["script"], (
        "Python bypass script was modified during load — ps_convert_to_oneliner "
        "must not run on non-powershell bypasses"
    )

    ps_yaml = yaml.safe_load(
        Path("empire/server/bypasses/SafeChecksPS.yaml").read_text()
    )
    safechecks_ps = bypasses_by_name.get("SafeChecksPS")
    assert safechecks_ps is not None, "SafeChecksPS bypass was not loaded"
    assert safechecks_ps.language == "powershell"
    assert safechecks_ps.code == ps_convert_to_oneliner(ps_yaml["script"]), (
        "PowerShell bypass script does not match ps_convert_to_oneliner output — "
        "the gate is not invoking the converter"
    )


def test_listener_template_loader(monkeypatch):
    sys.argv = ["", "server", "--config", SERVER_CONFIG_LOC]
    session_mock = MagicMock()
    monkeypatch.setattr(
        "empire.server.core.listener_template_service.SessionLocal", session_mock
    )

    session_mock.begin.return_value.__enter__.return_value.query.return_value.first.return_value.install_path = "empire/server"

    main_menu = Mock()
    main_menu.installPath = "empire/server"
    main_menu.install_path = Path("empire/server")

    listener_template_service = ListenerTemplateService(main_menu)

    min_template_count = 5
    assert len(listener_template_service.get_listener_templates()) > min_template_count


def test_stager_template_loader(monkeypatch):
    sys.argv = ["", "server", "--config", SERVER_CONFIG_LOC]
    session_mock = MagicMock()
    monkeypatch.setattr(
        "empire.server.core.stager_template_service.SessionLocal", session_mock
    )

    session_mock.begin.return_value.__enter__.return_value.query.return_value.first.return_value.install_path = "empire/server"

    main_menu = Mock()
    main_menu.installPath = "empire/server"
    main_menu.install_path = Path("empire/server")

    stager_template_service = StagerTemplateService(main_menu)

    min_template_count = 10
    assert len(stager_template_service.get_stager_templates()) > min_template_count


def test_profile_loader(monkeypatch):
    sys.argv = ["", "server", "--config", SERVER_CONFIG_LOC]
    session_mock = MagicMock()
    monkeypatch.setattr("empire.server.core.profile_service.SessionLocal", session_mock)

    session_mock.begin.return_value.__enter__.return_value.query.return_value.first.return_value.install_path = "empire/server"

    session_mock.begin.return_value.__enter__.return_value.query.return_value.filter.return_value.first.return_value = None

    main_menu = Mock()
    main_menu.installPath = "empire/server"
    main_menu.install_path = Path("empire/server")

    ProfileService(main_menu)

    min_call_count = 20
    assert (
        session_mock.begin.return_value.__enter__.return_value.add.call_count
        > min_call_count
    )
