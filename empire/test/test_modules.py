import logging
from unittest.mock import MagicMock, Mock

import pytest


def convert_options_to_params(options):
    params = {}
    for option in options:
        params[option.name] = option.value
    return params


def fake_obfuscate(psScript, obfuscationCommand):
    return psScript


def test_load_modules(monkeypatch, caplog, db):
    """
    This is just meant to be a small smoke test to ensure that the modules
    that come with Empire can be loaded properly at startup and a script can
    be generated with the default values.
    """
    from empire.server.core.module_service import ModuleService

    caplog.set_level(logging.DEBUG)

    main_menu = Mock()
    main_menu.installPath = "empire/server"

    main_menu.obfuscationv2 = Mock()
    obf_conf_mock = MagicMock()
    main_menu.obfuscationv2.get_obfuscation_config = Mock(
        side_effect=lambda x, y: obf_conf_mock
    )
    main_menu.obfuscationv2.obfuscate = Mock(side_effect=fake_obfuscate)
    main_menu.obfuscationv2.obfuscate_keywords = Mock(side_effect=lambda x: x)

    modules = ModuleService(main_menu)

    # Fail if a module fails to load.
    messages = [x.message for x in caplog.records if x.levelno >= logging.WARNING]
    if messages:
        pytest.fail("warning messages encountered during testing: {}".format(messages))

    assert len(modules.modules) > 0

    for key, module in modules.modules.items():
        if not module.advanced.custom_generate:
            resp, err = modules._generate_script(
                db, module, convert_options_to_params(module.options), None
            )

            # not gonna bother mocking out the csharp server right now.
            if err != "csharpserver plugin not running":
                # fail if a module fails to generate a script.
                assert (
                    resp is not None and len(resp) > 0
                ), f"No generated script for module {key}"
