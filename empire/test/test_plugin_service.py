import logging
import os
import shutil
from contextlib import contextmanager
from unittest.mock import MagicMock

from empire.server.api.v2.plugin.plugin_dto import PluginExecutePostRequest


@contextmanager
def patch_plugin_execute(plugin, execute_func):
    old_execute = plugin.execute
    plugin.execute = execute_func
    yield
    plugin.execute = old_execute


@contextmanager
def temp_copy_plugin(plugin_path):
    """
    Copy the example plugin to a temporary location. Since plugin_service
    won't load a plugin called "example".
    """
    example_plugin_path = os.path.join(plugin_path, "example.plugin")
    example_plugin_copy_path = os.path.join(plugin_path, "temporary.plugin")

    # copy example plugin to a new location
    shutil.copyfile(example_plugin_path, example_plugin_copy_path)

    yield

    # remove the temporary copy
    os.remove(example_plugin_copy_path)


def test_autostart_plugins(caplog, monkeypatch, db, models, empire_config):
    caplog.set_level(logging.DEBUG)

    from empire.server.core.plugin_service import PluginService

    plugin_path = db.query(models.Config).first().install_path + "/plugins"

    with temp_copy_plugin(plugin_path):
        main_menu_mock = MagicMock()
        plugin_service = PluginService(main_menu_mock)
        plugin_service.startup()

    assert "This function has been called 1 times." in caplog.text


# No kwargs pre 5.2
def test_plugin_execute_without_kwargs():
    from empire.server.core.plugin_service import PluginService

    def execute(options):
        return f"This function was called with options: {options}"

    main_menu_mock = MagicMock()
    plugin_service = PluginService(main_menu_mock)
    plugin_service.startup()

    plugin = plugin_service.get_by_id("basic_reporting")
    with patch_plugin_execute(plugin, execute):
        req = PluginExecutePostRequest(options={"report": "session"})
        res, err = plugin_service.execute_plugin(None, plugin, req, None)

    assert res == execute(req.options)


def test_plugin_execute_with_kwargs():
    from empire.server.core.plugin_service import PluginService

    def execute(options, **kwargs):
        return f"This function was called with options: {options} and kwargs: {kwargs}"

    main_menu_mock = MagicMock()
    plugin_service = PluginService(main_menu_mock)
    plugin_service.startup()

    plugin = plugin_service.get_by_id("basic_reporting")
    with patch_plugin_execute(plugin, execute):
        req = PluginExecutePostRequest(options={"report": "session"})
        res, err = plugin_service.execute_plugin("db_session", plugin, req, 1)

    assert res == execute(req.options, db="db_session", user=1)
