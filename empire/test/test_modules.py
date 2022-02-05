from unittest.mock import MagicMock, Mock


def convert_options_to_params(options):
    params = {}
    for option in options:
        params[option.name] = option.value
    return params


def fake_obfuscate(installPath, psScript, obfuscationCommand):
    return psScript


def test_load_modules(monkeypatch, capsys):
    """
    This is just meant to be a small smoke test to ensure that the modules
    that come with Empire can be loaded properly at startup and a script can
    be generated with the default values.
    """
    monkeypatch.setattr(
        "empire.server.v2.core.module_service.SessionLocal", MagicMock()
    )

    data_util_mock = Mock()
    data_util_mock.obfuscate = Mock(side_effect=fake_obfuscate)
    data_util_mock.keyword_obfuscation = Mock(side_effect=lambda x: x)
    monkeypatch.setattr(
        "empire.server.v2.core.module_service.data_util", data_util_mock
    )

    from empire.server.v2.core.module_service import ModuleService

    main_menu = Mock()
    main_menu.installPath = "empire/server"

    agent_mock = Mock()
    agent_mock.language_version = "7.0"
    main_menu.agents.get_agent_db.return_value = agent_mock

    modules = ModuleService(main_menu)

    # Fail if a module fails to load.
    if capsys:
        out, err = capsys.readouterr()
        assert "Error loading module" not in out

    for key, module in modules.modules.items():
        if not module.advanced.custom_generate:
            resp, err = modules._generate_script(
                module, convert_options_to_params(module.options), 1
            )

            # not gonna bother mocking out the csharp server right now.
            if err != "csharpserver plugin not running":
                # fail if a module fails to generate a script.
                assert (
                    resp is not None and len(resp) > 0
                ), f"No generated script for module {key}"
