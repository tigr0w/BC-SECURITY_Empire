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
def patch_plugin_options(plugin, options):
    old_options = plugin.options
    plugin.options = options
    yield
    plugin.options = old_options


@contextmanager
def temp_copy_plugin(plugin_path):
    """
    Copy the example plugin to a temporary location. Since plugin_service
    won't load a plugin called "example".
    """
    example_plugin_path = plugin_path / "example.plugin"
    example_plugin_copy_path = plugin_path / "temporary.plugin"

    # copy example plugin to a new location
    shutil.copyfile(str(example_plugin_path), str(example_plugin_copy_path))

    yield

    # remove the temporary copy
    os.remove(example_plugin_copy_path)


def test_autostart_plugins(
    caplog, monkeypatch, db, models, empire_config, install_path
):
    caplog.set_level(logging.DEBUG)

    from empire.server.core.plugin_service import PluginService

    plugin_path = install_path / "plugins"

    with temp_copy_plugin(plugin_path):
        main_menu_mock = MagicMock()
        main_menu_mock.installPath = str(install_path)
        plugin_service = PluginService(main_menu_mock)
        plugin_service.startup()

    assert "This function has been called 1 times." in caplog.text


# No kwargs pre 5.2
def test_plugin_execute_without_kwargs(install_path):
    from empire.server.core.plugin_service import PluginService

    def execute(options):
        return f"This function was called with options: {options}"

    main_menu_mock = MagicMock()
    main_menu_mock.installPath = install_path
    plugin_service = PluginService(main_menu_mock)
    plugin_service.startup()

    plugin = plugin_service.get_by_id("basic_reporting")
    with patch_plugin_execute(plugin, execute):
        req = PluginExecutePostRequest(options={"report": "session"})
        res, err = plugin_service.execute_plugin(None, plugin, req, None)

    assert res == execute(req.options)


def test_plugin_execute_with_kwargs(install_path):
    from empire.server.core.plugin_service import PluginService

    def execute(options, **kwargs):
        return f"This function was called with options: {options} and kwargs: {kwargs}"

    main_menu_mock = MagicMock()
    main_menu_mock.installPath = install_path
    plugin_service = PluginService(main_menu_mock)
    plugin_service.startup()

    plugin = plugin_service.get_by_id("basic_reporting")
    with patch_plugin_execute(plugin, execute):
        req = PluginExecutePostRequest(options={"report": "session"})
        res, err = plugin_service.execute_plugin("db_session", plugin, req, 1)

    assert res == execute(req.options, db="db_session", user=1)


def test_execute_plugin_file_option_not_found(install_path, db):
    from empire.server.core.plugin_service import PluginService

    main_menu_mock = MagicMock()
    main_menu_mock.installPath = install_path

    main_menu_mock.downloadsv2 = MagicMock()
    main_menu_mock.downloadsv2.get_by_id.return_value = None

    plugin_service = PluginService(main_menu_mock)
    plugin_service.startup()

    plugin = plugin_service.get_by_id("basic_reporting")

    with patch_plugin_options(
        plugin,
        {
            "file_option": {
                "Name": "file_option",
                "Description": "File option",
                "Type": "File",
                "Strict": False,
                "Required": True,
            }
        },
    ):
        req = PluginExecutePostRequest(options={"file_option": 9999})

        try:
            plugin_service.execute_plugin(db, plugin, req, None)
        except Exception as e:
            assert str(e) == "File not found for 'file_option' id 9999"


def test_execute_plugin_file_option(install_path, db, models):
    from empire.server.core.plugin_service import PluginService

    main_menu_mock = MagicMock()
    main_menu_mock.installPath = install_path

    download = models.Download(id=9999, filename="test_file", location="/tmp/test_file")
    main_menu_mock.downloadsv2 = MagicMock()
    main_menu_mock.downloadsv2.get_by_id.return_value = download

    plugin_service = PluginService(main_menu_mock)
    plugin_service.startup()

    plugin = plugin_service.get_by_id("basic_reporting")

    mocked_execute = MagicMock()
    mocked_execute.return_value = "success"

    with patch_plugin_options(
        plugin,
        {
            "file_option": {
                "Name": "file_option",
                "Description": "File option",
                "Type": "File",
                "Strict": False,
                "Required": True,
            }
        },
    ), patch_plugin_execute(plugin, mocked_execute):
        req = PluginExecutePostRequest(options={"file_option": "9999"})
        res, err = plugin_service.execute_plugin(db, plugin, req, None)

        assert err is None
        assert res == "success"
        mocked_execute.assert_called_once_with(
            {"file_option": download}, db=db, user=None
        )
