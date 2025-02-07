from pathlib import Path
from unittest.mock import Mock

import pytest

from empire.server.core.exceptions import ModuleValidationException


@pytest.fixture(scope="module")
def main_menu_mock(models, install_path):
    main_menu = Mock()
    main_menu.installPath = install_path
    main_menu.install_path = Path(install_path)
    main_menu.listeners.activeListeners = {}
    main_menu.listeners.listeners = {}
    main_menu.obfuscationv2 = Mock()
    main_menu.obfuscationv2.get_obfuscation_config = Mock(
        return_value=models.ObfuscationConfig(
            language="python", command="", enabled=False
        )
    )
    main_menu.obfuscationv2.obfuscate_keywords = Mock(side_effect=lambda x: x)
    return main_menu


@pytest.fixture
def module_service(main_menu_mock):
    from empire.server.core.module_service import ModuleService

    return ModuleService(main_menu=main_menu_mock)


@pytest.fixture
def agent_mock():
    agent_mock = Mock()
    agent_mock.session_id = "ABC123"
    return agent_mock


def test_execute_module_with_script_in_yaml_modified_python_agent(
    module_service, agent_mock
):
    agent_mock.language = "python"
    params = {
        "Agent": agent_mock.session_id,
        "Text": "Hello World",
    }
    module_id = "python_trollsploit_osx_say"
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, "Modified Script: {{ Text }}"
    )

    assert err is None
    script = res.data

    assert script == "Modified Script: Hello World"


def test_execute_module_with_script_in_path_powershell_agent(
    module_service, agent_mock
):
    agent_mock.language = "powershell"
    params = {
        "Agent": agent_mock.session_id,
        "BooSource": "Hello World",
    }
    module_id = "powershell_code_execution_invoke_boolang"
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )

    assert err is None
    script = res.data

    assert script.startswith("function Invoke-Boolang")


def test_execute_module_with_script_in_path_modified_powershell(
    module_service, agent_mock
):
    agent_mock.language = "powershell"
    params = {
        "Agent": agent_mock.session_id,
        "BooSource": "Hello World",
    }
    module_id = "powershell_code_execution_invoke_boolang"
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, "Modified Script: "
    )

    assert err is None
    script = res.data

    assert script.startswith(
        'Modified Script:  Invoke-Boolang -BooSource "Hello World"'
    )


def test_execute_module_custom_generate_no_obfuscation_config_powershell_agent(
    main_menu_mock, module_service, agent_mock
):
    agent_mock.language = "powershell"
    params = {"Agent": agent_mock.session_id}
    module_id = "python_collection_osx_search_email"

    main_menu_mock.obfuscationv2.get_obfuscation_config = Mock(
        side_effect=lambda x, y: None
    )
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )

    assert err is None
    script = res.data

    assert script == 'cmd = "find /Users/ -name *.emlx 2>/dev/null"\nrun_command(cmd)'


def test_execute_module_task_command_python_agent(module_service, agent_mock):
    agent_mock.language = "python"
    params = {
        "Agent": agent_mock.session_id,
        "Text": "Hello World",
    }
    module_id = "python_trollsploit_osx_say"
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )

    assert err is None

    script = res.data
    assert script == "run_command('say -v alex Hello World')"

    task_command = res.command
    assert task_command == "TASK_PYTHON_CMD_WAIT"


def test_execute_module_task_command_ironpython_agent(module_service, agent_mock):
    agent_mock.language = "ironpython"
    params = {
        "Agent": agent_mock.session_id,
        "Text": "Hello World",
    }
    module_id = "python_trollsploit_osx_say"
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )

    assert err is None
    task_command = res.command
    assert task_command == "TASK_PYTHON_CMD_WAIT"


def test_execute_module_task_command_csharp_agent_with_missing_csharp_module(
    module_service, agent_mock
):
    agent_mock.language = "csharp"
    params = {
        "Agent": agent_mock.session_id,
        "Text": "Hello World",
    }
    module_id = "csharp_execution_some_module"
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )

    assert err == "Module not found for id csharp_execution_some_module"


def test_execute_module_task_command_csharp_agent_with_csharp_module(
    module_service, agent_mock
):
    agent_mock.language = "csharp"
    params = {
        "Agent": agent_mock.session_id,
        "Command": "triage",
    }
    module_id = "csharp_credentials_rubeus"
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )

    assert err is None
    task_command = res.command
    assert task_command == "TASK_CSHARP_CMD_JOB"


def test_execute_module_bof_custom_generate(module_service, agent_mock):
    agent_mock.language = "csharp"
    params = {
        "Agent": agent_mock.session_id,
        "Architecture": "x64",
        "Domain": ".",
    }
    module_id = "bof_situational_awareness_adcs_enum"
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )

    assert err is None
    task_command = res.command
    assert task_command == "TASK_CSHARP_CMD_WAIT"


def test_execute_module_bof(module_service, agent_mock):
    agent_mock.language = "csharp"
    params = {
        "Agent": agent_mock.session_id,
        "Architecture": "x64",
        "Server": ".",
    }
    module_id = "bof_situational_awareness_tasklist"
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )

    assert err is None
    task_command = res.command
    assert task_command == "TASK_CSHARP_CMD_WAIT"


def test_execute_bof_module_missing_architecture(module_service, agent_mock):
    agent_mock.language = "csharp"
    params = {
        "Agent": agent_mock.session_id,
        "Architecture": "",
        "Server": ".",
    }
    module_id = "bof_situational_awareness_tasklist"

    with pytest.raises(ModuleValidationException) as excinfo:
        module_service.execute_module(
            None, agent_mock, module_id, params, True, True, None
        )

    assert "required option missing: Architecture" in str(excinfo.value)


def test_execute_csharp_module(module_service, agent_mock):
    agent_mock.language = "csharp"
    params = {
        "Agent": agent_mock.session_id,
        "Password": "password",
        "Port": "5900",
        "Username": "Empire",
    }
    module_id = "csharp_management_vnc"

    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )

    assert err is None
    task_command = res.command
    assert task_command == "TASK_CSHARP_CMD_WAIT"


def test_execute_bof_module_missing_option(module_service, agent_mock):
    agent_mock.language = "csharp"
    params = {
        "Agent": agent_mock.session_id,
        "Password": "password",
        "Port": "",
        "Username": "Empire",
    }
    module_id = "csharp_management_vnc"

    with pytest.raises(ModuleValidationException) as excinfo:
        module_service.execute_module(
            None, agent_mock, module_id, params, True, True, None
        )

    assert "required option missing: Port" in str(excinfo.value)


def test_execute_module_task_command_powershell_agent(module_service, agent_mock):
    agent_mock.language = "powershell"
    params = {
        "Agent": agent_mock.session_id,
        "BooSource": "Hello World",
    }
    module_id = "powershell_code_execution_invoke_boolang"
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )

    assert err is None
    task_command = res.command
    assert task_command == "TASK_POWERSHELL_CMD_JOB"


def test_execute_module_task_command_unsupported_agent_language(
    module_service, agent_mock
):
    agent_mock.language = "unsupported_language"
    params = {
        "Agent": agent_mock.session_id,
        "BooSource": "Hello World",
    }
    module_id = "powershell_code_execution_invoke_boolang"
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )

    assert res is None
    assert err == "Unsupported agent language: unsupported_language"


def test_execute_module_with_non_ascii_characters(module_service, agent_mock):
    agent_mock.language = "python"
    params = {
        "Agent": agent_mock.session_id,
        "Text": "こんにちは世界",
    }
    module_id = "python_trollsploit_osx_say"

    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )

    assert err is None
    assert res.data


def test_execute_disabled_module(module_service, agent_mock):
    agent_mock.language = "python"
    params = {
        "Agent": agent_mock.session_id,
        "Text": "Hello World",
    }
    module_id = "python_trollsploit_osx_say"

    module = module_service.get_by_id(module_id)
    module.enabled = False

    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )

    assert res is None
    assert err == "Cannot execute disabled module"


def test_execute_module_validation_error(module_service, agent_mock):
    agent_mock.language = "python"
    params = {
        "InvalidParam": "invalid_value",
    }
    module_id = "python_trollsploit_osx_say"

    with pytest.raises(ModuleValidationException) as excinfo:
        module_service.execute_module(
            None, agent_mock, module_id, params, True, True, None
        )

    assert "required option missing: Agent" in str(excinfo.value)


def test_execute_module_with_empty_params(module_service, agent_mock):
    agent_mock.language = "python"
    params = {}
    module_id = "python_trollsploit_osx_say"

    with pytest.raises(ModuleValidationException) as excinfo:
        module_service.execute_module(
            None, agent_mock, module_id, params, True, True, None
        )

    assert "required option missing: Agent" in str(excinfo.value)
