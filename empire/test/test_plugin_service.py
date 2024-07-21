import logging
from contextlib import contextmanager
from unittest.mock import MagicMock, Mock, patch

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
def patch_plugin_class_on_start_on_stop(plugin_class, on_start=None, on_stop=None):
    with patch.object(plugin_class, "on_start", new=on_start), patch.object(
        plugin_class, "on_stop", new=on_stop
    ):
        yield


def test_auto_execute_plugins(
    caplog, monkeypatch, db, models, empire_config, install_path
):
    caplog.set_level(logging.DEBUG)

    from empire.server.core.plugin_service import PluginService

    main_menu_mock = MagicMock()
    main_menu_mock.installPath = str(install_path)
    plugin_service = PluginService(main_menu_mock)
    plugin_service.startup()

    assert "This function has been called 1 times." in caplog.text
    assert "Message: Hello World!" in caplog.text


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


def test_on_start_on_stop_called(install_path):
    from empire.server.core.plugin_service import PluginService
    from empire.server.core.plugins import BasePlugin

    main_menu_mock = MagicMock()
    main_menu_mock.installPath = install_path

    plugin_service = PluginService(main_menu_mock)
    plugin_service.startup()

    on_start_mock = Mock()
    on_stop_mock = Mock()

    # Need to patch the class itself, not the instance
    # To capture the on_start.
    with patch_plugin_class_on_start_on_stop(
        BasePlugin, on_start=on_start_mock, on_stop=on_stop_mock
    ):
        plugin_service.startup()
        assert on_start_mock.call_count > 0

        plugin_service.shutdown()
        assert on_stop_mock.call_count > 0


def test_on_load_on_unload_called(install_path):
    pass
