import logging
import os
import shutil
from contextlib import contextmanager
from unittest.mock import MagicMock


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
