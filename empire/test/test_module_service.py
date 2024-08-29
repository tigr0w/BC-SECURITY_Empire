from unittest.mock import Mock

import pytest


@pytest.fixture(scope="module")
def main_menu_mock(db, models, install_path):
    main_menu = Mock()
    main_menu.installPath = install_path
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


@pytest.fixture(scope="module")
def module_service(main_menu_mock):
    from empire.server.core.module_service import ModuleService

    return ModuleService(main_menu=main_menu_mock)


@pytest.fixture(scope="module")
def agent_mock():
    agent_mock = Mock()
    agent_mock.session_id = "ABC123"

    return agent_mock


def test_execute_module_script_in_yaml(module_service, agent_mock):
    params = {
        "Agent": agent_mock.session_id,
        "Text": "Hello World",
    }
    module_id = "python_trollsploit_osx_say"
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )

    assert err is None
    script = res["data"]

    assert script == "run_command('say -v alex Hello World')"


def test_execute_module_with_script_in_yaml_modified(module_service, agent_mock):
    params = {
        "Agent": agent_mock.session_id,
        "Text": "Hello World",
    }
    module_id = "python_trollsploit_osx_say"
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, "Modified Script: {{ Text }}"
    )

    assert err is None
    script = res["data"]

    assert script == "Modified Script: Hello World"


def test_execute_module_with_script_in_path(module_service, agent_mock):
    params = {
        "Agent": agent_mock.session_id,
        "BooSource": "Hello World",
    }
    module_id = "powershell_code_execution_invoke_boolang"
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )

    assert err is None
    script = res["data"]

    assert script.startswith("function Invoke-Boolang")


def test_execute_module_with_script_in_path_modified(module_service, agent_mock):
    params = {
        "Agent": agent_mock.session_id,
        "BooSource": "Hello World",
    }
    module_id = "powershell_code_execution_invoke_boolang"
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, "Modified Script: "
    )

    assert err is None
    script = res["data"]

    assert script.startswith(
        'Modified Script:  Invoke-Boolang -BooSource "Hello World"'
    )


def test_execute_module_custom_generate_no_obfuscation_config(
    main_menu_mock, module_service, agent_mock
):
    params = {"Agent": agent_mock.session_id}
    module_id = "python_collection_osx_search_email"

    main_menu_mock.obfuscationv2.get_obfuscation_config = Mock(
        side_effect=lambda x, y: None
    )
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )

    assert err is None
    script = res["data"]

    assert script == 'cmd = "find /Users/ -name *.emlx 2>/dev/null"\nrun_command(cmd)'
