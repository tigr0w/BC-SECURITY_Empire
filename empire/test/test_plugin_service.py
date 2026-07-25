import logging
import shutil
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, Mock, patch

import pytest

from empire.server.api.v2.plugin.plugin_dto import PluginExecutePostRequest
from empire.server.core.config.config_manager import (
    PluginAutoExecuteConfig,
    PluginConfig,
)
from empire.server.core.db import models as db_models
from empire.server.core.db.models import PluginInfo
from empire.server.core.exceptions import PluginValidationException
from empire.server.core.plugin_service import PluginHolder, PluginService
from empire.server.core.plugins import BasePlugin

if TYPE_CHECKING:
    from empire.server.common.empire import MainMenu


@contextmanager
def patch_plugin_execute(plugin, execute_func):
    old_execute = plugin.execute
    plugin.execute = execute_func
    yield
    plugin.execute = old_execute


@contextmanager
def patch_plugin_options(plugin, options):
    old_options = plugin.execution_options
    plugin.execution_options = options
    yield
    plugin.execution_options = old_options


@contextmanager
def patch_plugin_class_on_start_on_stop(plugin_class, on_start=None, on_stop=None):
    with (
        patch.object(plugin_class, "on_start", new=on_start),
        patch.object(plugin_class, "on_stop", new=on_stop),
    ):
        yield


@contextmanager
def patch_plugin_class_on_load_on_unload(plugin_class, on_load=None, on_unload=None):
    with (
        patch.object(plugin_class, "on_load", new=on_load),
        patch.object(plugin_class, "on_unload", new=on_unload),
    ):
        yield


def test_auto_execute_plugins(caplog, monkeypatch, models, empire_config, install_path):
    caplog.set_level(logging.DEBUG)

    plugin_service = _service(install_path)
    plugin_service.startup()

    assert "This function has been called 1 times." in caplog.text
    assert "Message: Hello World!" in caplog.text


def test_plugin_execute_with_kwargs(session_local, install_path):
    def execute(options, **kwargs):
        return f"This function was called with options: {options} and kwargs: {kwargs}"

    plugin_service = _service(install_path)
    plugin_service.startup()

    with session_local.begin() as db:
        plugin_holder = plugin_service.get_by_id(db, "basic_reporting")
        plugin = plugin_holder.loaded_plugin
        with patch_plugin_execute(plugin, execute):
            req = PluginExecutePostRequest(options={"report": "session"})
            res = plugin_service.execute_plugin("db_session", plugin, req, 1)

    assert res == execute(req.options, db="db_session", user=1)


def test_execute_plugin_file_option_not_found(install_path, session_local):
    plugin_service = _service(install_path)
    plugin_service.download_service.get_by_id.return_value = None
    plugin_service.startup()

    with session_local.begin() as db:
        plugin_holder = plugin_service.get_by_id(db, "basic_reporting")
        plugin = plugin_holder.loaded_plugin

    with patch_plugin_options(
        plugin,
        {
            "file_option": {
                "Name": "file_option",
                "Description": "File option",
                "Type": "File",
                "Strict": False,
                "Required": True,
                "DependsOn": None,
            }
        },
    ):
        req = PluginExecutePostRequest(options={"file_option": 9999})

        with pytest.raises(PluginValidationException) as e:
            plugin_service.execute_plugin(db, plugin, req, None)
        assert str(e.value) == "File not found for 'file_option' id 9999"


def test_execute_plugin_file_option(install_path, session_local, models):
    download = models.Download(id=9999, filename="test_file", location="/tmp/test_file")
    plugin_service = _service(install_path)
    plugin_service.download_service.get_by_id.return_value = download
    plugin_service.startup()

    with session_local.begin() as db:
        plugin_holder = plugin_service.get_by_id(db, "basic_reporting")
        plugin = plugin_holder.loaded_plugin

    mocked_execute = MagicMock()
    mocked_execute.return_value = "success"

    with (
        patch_plugin_options(
            plugin,
            {
                "file_option": {
                    "Name": "file_option",
                    "Description": "File option",
                    "Type": "File",
                    "Strict": False,
                    "Required": True,
                    "DependsOn": None,
                }
            },
        ),
        patch_plugin_execute(plugin, mocked_execute),
    ):
        req = PluginExecutePostRequest(options={"file_option": "9999"})
        with session_local.begin() as db:
            res = plugin_service.execute_plugin(db, plugin, req, None)

            assert res == "success"
            mocked_execute.assert_called_once_with(
                {"file_option": download},
                db=db,
                user=None,
            )


# Note this test is not great. If all plugins are overriding the on_start and on_stop
# then it will fail.
def test_on_start_on_stop_called(install_path):
    plugin_service = _service(install_path)
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


# Note this test is not great. If all plugins are overriding the on_load and on_unload
# then it will fail.
def test_on_load_on_unload_called(install_path):
    plugin_service = _service(install_path)
    plugin_service.startup()

    on_load_mock = Mock()
    on_unload_mock = Mock()

    # Need to patch the class itself, not the instance
    # To capture the on_load.
    with patch_plugin_class_on_load_on_unload(
        BasePlugin, on_load=on_load_mock, on_unload=on_unload_mock
    ):
        plugin_service.startup()
        assert on_load_mock.call_count > 0

        plugin_service.shutdown()
        assert on_unload_mock.call_count > 0


@pytest.fixture(scope="module")
def plugin_service(main: "MainMenu"):
    return main.pluginsv2


def test__determine_auto_start(empire_config, plugin_service):
    plugin_info = PluginInfo(
        id="test_auto_start", name="TestAutoStart", auto_start=False, main=""
    )

    empire_config_tmp = empire_config.model_copy()
    empire_config_tmp.plugins["test_auto_start"] = PluginConfig()

    # Test with plugin config False and server config empty
    # Should use plugin config value
    assert plugin_service._determine_auto_start(plugin_info, empire_config_tmp) is False

    # Test with plugin config false and server config true
    # Should use server config value
    empire_config_tmp.plugins["test_auto_start"].auto_start = True
    assert plugin_service._determine_auto_start(plugin_info, empire_config_tmp) is True


def test__determine_auto_execute(empire_config, plugin_service):
    plugin_config = PluginInfo(
        id="test_auto_execute", name="TestAutoExecute", auto_execute=None, main=""
    )

    # Test with plugin config None and server config None
    # Should use default value (None)
    assert plugin_service._determine_auto_execute(plugin_config, empire_config) is None

    # Test with plugin config None and server config true
    # Should use server config value
    empire_config.plugins["test_auto_execute"] = PluginConfig(
        auto_execute=PluginAutoExecuteConfig(enabled=True)
    )
    assert (
        plugin_service._determine_auto_execute(plugin_config, empire_config)
        is empire_config.plugins["test_auto_execute"].auto_execute
    )

    # Test with plugin config true and server_config None
    # Should use plugin config value
    plugin_config.auto_execute = PluginAutoExecuteConfig(enabled=True)
    empire_config.plugins["test_auto_execute"] = PluginConfig(auto_execute=None)
    assert (
        plugin_service._determine_auto_execute(plugin_config, empire_config)
        is plugin_config.auto_execute
    )


class _LifecycleSpy:
    """Stand-in for a loaded plugin that records `enabled` as each hook sees it."""

    def __init__(self, name="spy", raise_on=(), enabled=False):
        self.name = name
        # A collection, so "raises in on_stop *and* on_unload" is expressible.
        self.raise_on = {raise_on} if isinstance(raise_on, str) else set(raise_on)
        self.enabled = enabled
        self.calls = []
        self.enabled_during = {}

    def _record(self, hook):
        self.calls.append(hook)
        self.enabled_during[hook] = self.enabled
        if hook in self.raise_on:
            raise ConnectionRefusedError(f"{self.name} {hook} blew up")

    def on_start(self, db):
        self._record("on_start")

    def on_stop(self, db):
        self._record("on_stop")

    def on_unload(self, db):
        self._record("on_unload")


def _holder(plugin):
    # model_construct skips validation so the spy doesn't have to be a real
    # BasePlugin / models.Plugin pair.
    return PluginHolder.model_construct(
        loaded_plugin=plugin, db_plugin=SimpleNamespace(enabled=False)
    )


def _service(install_path):
    main_menu_mock = MagicMock()
    main_menu_mock.install_path = Path(install_path)
    return PluginService(main_menu_mock)


def _isolated_service(install_path, tmp_path, *plugin_ids):
    """A PluginService that scans private copies of FooPluginTemplate.

    The load-path tests patch BasePlugin hooks globally, so they must stay off
    the real plugin/marketplace dirs or they leave the bundled plugins disabled
    for every test that runs afterwards. Each copy is renamed off "foo" so it
    gets its own plugin row and cannot collide with test_plugin_api's fixtures.
    FooPluginTemplate, not FooPlugin: only the template is tracked in git.
    """
    source = Path(install_path).parent / "test/plugin_install/FooPluginTemplate"
    plugins_dir = tmp_path / "plugins"
    for plugin_id in plugin_ids:
        dest = plugins_dir / plugin_id
        shutil.copytree(source, dest)
        plugin_yaml = dest / "plugin.yaml"
        plugin_yaml.write_text(
            plugin_yaml.read_text().replace("name: foo", f"name: {plugin_id}", 1)
        )

    service = _service(install_path)
    # Both, so nothing reaches for the real data dir even though the override
    # below means neither is scanned.
    service.plugin_path = plugins_dir
    service.marketplace_path = tmp_path / "marketplace"
    service.marketplace_path.mkdir()
    # Fixed order: iterdir() is unsorted, so "a plugin blowing up does not stop
    # the ones after it" would quietly weaken into "...the ones before it".
    service._list_plugin_directories = lambda: [plugins_dir / p for p in plugin_ids]
    return service


@pytest.mark.parametrize(
    ("raise_on", "expected_log"),
    [
        ("on_stop", "Plugin bad failed to stop"),
        ("on_unload", "Plugin bad failed to unload"),
    ],
)
def test_shutdown_isolates_a_plugin_that_raises(
    install_path, session_local, caplog, raise_on, expected_log
):
    """One plugin's teardown blowing up must not skip the plugins after it."""
    plugin_service = _service(install_path)
    bad = _LifecycleSpy("bad", raise_on=raise_on)
    good = _LifecycleSpy("good")
    plugin_service.loaded_plugins = {"bad": bad, "good": good}

    with caplog.at_level(logging.ERROR):
        plugin_service.shutdown()

    # The raising plugin still gets unloaded, and `good` is reached at all.
    assert bad.calls == ["on_stop", "on_unload"]
    assert good.calls == ["on_stop", "on_unload"]
    assert expected_log in caplog.text
    assert "good failed" not in caplog.text


def test_shutdown_clears_enabled_before_on_stop(install_path, session_local):
    """A plugin joining a `while self.enabled` thread in on_stop must not hang."""
    plugin_service = _service(install_path)
    # Constructed enabled, or the assertion below passes vacuously.
    plugin = _LifecycleSpy("running", enabled=True)
    plugin_service.loaded_plugins = {"running": plugin}

    plugin_service.shutdown()

    assert plugin.enabled_during["on_stop"] is False
    assert plugin.enabled is False


def test_shutdown_survives_a_plugin_mutating_loaded_plugins(
    install_path, session_local
):
    """A plugin holds a reference to the service, so it can mutate the dict."""
    plugin_service = _service(install_path)
    good = _LifecycleSpy("good")

    class _Mutator(_LifecycleSpy):
        def on_stop(self, db):
            plugin_service.loaded_plugins["late_arrival"] = _LifecycleSpy("late")
            super().on_stop(db)

    plugin_service.loaded_plugins = {"mutator": _Mutator("mutator"), "good": good}

    # Without the list() snapshot this raises RuntimeError from the iterator,
    # outside the per-hook try blocks, and `good` is never torn down.
    plugin_service.shutdown()

    assert good.calls == ["on_stop", "on_unload"]


def test_shutdown_isolates_a_failure_from_the_session_itself(
    install_path, session_local, caplog
):
    """The session's commit fires at block exit, outside the per-hook handlers.

    A plugin that returns cleanly from on_stop having left a row that fails to
    flush raises from the `with` block's __exit__, which the inner try blocks
    never see. Opening the session can fail the same way -- at shutdown the
    pool may already be going away. Either one used to abort the teardown of
    every plugin after it.
    """
    plugin_service = _service(install_path)
    first = _LifecycleSpy("first")
    second = _LifecycleSpy("second")
    plugin_service.loaded_plugins = {"first": first, "second": second}

    @contextmanager
    def commit_fails_at_exit():
        yield MagicMock()
        raise RuntimeError("could not flush the plugin row")

    with (
        # The module-level name, not SessionLocal.begin: patching the attribute
        # mutates the shared sessionmaker, so every other thread in the process
        # -- the session-scoped app's listeners included -- gets this stub too.
        patch(
            "empire.server.core.plugin_service.SessionLocal",
            SimpleNamespace(begin=commit_fails_at_exit),
        ),
        caplog.at_level(logging.ERROR),
    ):
        plugin_service.shutdown()

    assert first.calls == ["on_stop", "on_unload"]
    assert second.calls == ["on_stop", "on_unload"]
    assert "first teardown failed" in caplog.text
    assert "second teardown failed" in caplog.text


def test_shutdown_stops_the_worker_even_if_no_session_can_be_opened(
    install_path, caplog
):
    """Clearing `enabled` is what stops a worker, so it can't need a session.

    At shutdown the pool may already be going away, and a plugin whose thread
    loops on `while self.enabled` would then never exit.
    """
    plugin_service = _service(install_path)
    plugin = _LifecycleSpy("running", enabled=True)
    plugin_service.loaded_plugins = {"running": plugin}

    def begin_fails():
        raise RuntimeError("the pool is already gone")

    with (
        patch(
            "empire.server.core.plugin_service.SessionLocal",
            SimpleNamespace(begin=begin_fails),
        ),
        caplog.at_level(logging.ERROR),
    ):
        plugin_service.shutdown()

    assert plugin.enabled is False
    assert "running teardown failed" in caplog.text


def test_shutdown_drops_the_plugins_it_unloaded(install_path, session_local):
    """Every object left in loaded_plugins has had on_unload called on it.

    /plugins/reload runs shutdown() then load_plugins(). Keeping the torn-down
    objects means a plugin that then fails to reload is still reported as
    loaded, and its stale object is what the API hands out.
    """
    plugin_service = _service(install_path)
    plugin_service.loaded_plugins = {"a": _LifecycleSpy("a"), "b": _LifecycleSpy("b")}

    plugin_service.shutdown()

    assert plugin_service.loaded_plugins == {}


def test_update_plugin_enabled_clears_a_stale_load_error(install_path):
    """A start that succeeds retires the reason the last one failed.

    load_plugin records `Failed to start: ...` and leaves the plugin loaded, so
    the operator can enable it again. Without the clear the row keeps the old
    reason next to `enabled: true` until the next restart.
    """
    plugin_service = _service(install_path)
    plugin = _LifecycleSpy()
    holder = _holder(plugin)
    holder.db_plugin.load_error = "Failed to start: boom"

    plugin_service.update_plugin_enabled(None, holder, True)

    assert holder.db_plugin.load_error is None


def test_update_plugin_enabled_flips_the_flag_before_the_hook(install_path):
    """Plugins guard background loops with `while self.enabled`."""
    plugin_service = _service(install_path)
    plugin = _LifecycleSpy()
    holder = _holder(plugin)

    plugin_service.update_plugin_enabled(None, holder, True)
    assert plugin.enabled_during["on_start"] is True
    assert holder.db_plugin.enabled is True

    plugin_service.update_plugin_enabled(None, holder, False)
    assert plugin.enabled_during["on_stop"] is False
    assert holder.db_plugin.enabled is False


def test_update_plugin_enabled_rolls_back_when_the_hook_raises(install_path):
    """A failed on_start leaves neither flag claiming the plugin is running."""
    plugin_service = _service(install_path)
    plugin = _LifecycleSpy(raise_on="on_start")
    holder = _holder(plugin)

    with pytest.raises(ConnectionRefusedError):
        plugin_service.update_plugin_enabled(None, holder, True)

    assert plugin.enabled is False
    assert holder.db_plugin.enabled is False


def test_update_plugin_enabled_does_not_claim_running_when_on_stop_raises(
    install_path,
):
    """A plugin whose on_stop failed must not advertise itself as running.

    The pre-flip means its worker has already seen `enabled = False` and very
    likely exited, so restoring the in-memory flag to True would let
    execute_plugin ("Plugin is not running" gates on exactly this) accept
    operator commands for a plugin with no worker. The row is restored so the
    operator can still retry.
    """
    plugin_service = _service(install_path)
    plugin = _LifecycleSpy(raise_on="on_stop", enabled=True)
    holder = _holder(plugin)
    holder.db_plugin.enabled = True

    with pytest.raises(ConnectionRefusedError):
        plugin_service.update_plugin_enabled(None, holder, False)

    assert plugin.enabled_during["on_stop"] is False
    assert plugin.enabled is False
    assert holder.db_plugin.enabled is True


def test_update_plugin_enabled_can_recover_a_stopped_plugin_whose_row_says_enabled(
    install_path,
):
    """The row and the loaded plugin diverge after a failed stop.

    Keying the short-circuit only on the row would make the operator's
    re-enable a silent no-op: the row already reads enabled, so nothing runs
    and the API still returns 200 with the plugin stopped.
    """
    plugin_service = _service(install_path)
    plugin = _LifecycleSpy(enabled=False)
    holder = _holder(plugin)
    holder.db_plugin.enabled = True

    plugin_service.update_plugin_enabled(None, holder, True)

    assert plugin.calls == ["on_start"]
    assert plugin.enabled is True


def test_update_plugin_enabled_rejects_a_plugin_that_is_not_loaded(install_path):
    """A plugin that failed to load has a row but no loaded_plugin."""
    plugin_service = _service(install_path)
    holder = PluginHolder.model_construct(
        loaded_plugin=None, db_plugin=SimpleNamespace(id="broken", enabled=False)
    )

    with pytest.raises(PluginValidationException):
        plugin_service.update_plugin_enabled(None, holder, False)


def test_load_plugin_sets_enabled_before_on_start(install_path, tmp_path):
    """Same ordering guarantee on the boot path as on the enable path."""
    plugin_service = _isolated_service(install_path, tmp_path, "foo_start_order")
    seen = []

    def on_start(self, db):
        seen.append(self.enabled)

    with patch.object(BasePlugin, "on_start", new=on_start):
        plugin_service.startup()

    assert seen, "expected at least one auto_start plugin to be started"
    assert all(seen)


def test_load_plugin_records_load_error_when_on_start_raises(
    install_path, session_local, tmp_path
):
    """A plugin that failed to start must not look like one an operator disabled."""
    plugin_id = "foo_load_error"
    plugin_service = _isolated_service(install_path, tmp_path, plugin_id)

    def on_start(self, db):
        raise ConnectionRefusedError("boom")

    with patch.object(BasePlugin, "on_start", new=on_start):
        plugin_service.startup()

    with session_local.begin() as db:
        holder = plugin_service.get_by_id(db, plugin_id)
        assert holder.db_plugin.enabled is False
        assert holder.loaded_plugin.enabled is False
        assert "boom" in (holder.db_plugin.load_error or "")


def test_load_plugins_skips_a_plugin_with_a_malformed_yaml(
    install_path, session_local, tmp_path
):
    """A bad plugin.yaml raises out of pydantic/yaml, not PluginValidationException.

    load_plugins runs from MainMenu.__init__, so letting that escape means the
    server does not boot at all.
    """
    plugin_service = _isolated_service(
        install_path, tmp_path, "foo_malformed", "foo_intact"
    )
    (plugin_service.plugin_path / "foo_malformed" / "plugin.yaml").write_text(
        "name: [unclosed\n"
    )

    plugin_service.startup()

    assert "foo_intact" in plugin_service.loaded_plugins
    assert "foo_malformed" not in plugin_service.loaded_plugins


def test_load_plugins_isolates_and_unloads_a_plugin_that_raises(
    install_path, session_local, tmp_path
):
    """One plugin blowing up at load must not stop the rest, or the server.

    The failure is injected through real plugin code (set_initial_options is
    the only third-party call that escapes load_plugin's own handlers) rather
    than by stubbing load_plugin, so this asserts the surviving plugin actually
    loads instead of asserting a particular method was called. __init__ has
    already run on_load by then, so the failed plugin also has to be unloaded:
    otherwise its hooks and listener templates stay registered against an
    object nothing can reach, and the duplicate registration makes the next
    /plugins/reload fail too.
    """
    plugin_service = _isolated_service(
        install_path, tmp_path, "foo_raises", "foo_survives"
    )
    unloaded = []
    real_set_initial_options = BasePlugin.set_initial_options

    def set_initial_options(self, db):
        if self.info.id == "foo_raises":
            raise RuntimeError("bad plugin settings")
        return real_set_initial_options(self, db)

    def on_unload(self, db):
        unloaded.append(self.info.id)

    with (
        patch.object(BasePlugin, "set_initial_options", new=set_initial_options),
        patch.object(BasePlugin, "on_unload", new=on_unload),
    ):
        plugin_service.startup()

    assert "foo_survives" in plugin_service.loaded_plugins
    assert "foo_raises" not in plugin_service.loaded_plugins
    assert unloaded == ["foo_raises"], (
        "on_unload has to run, or on_load's registrations are never released"
    )

    # The savepoint rolled back the row load_plugin inserted, so the failure is
    # only visible if load_plugins re-recorded it.
    with session_local.begin() as db:
        holder = plugin_service.get_by_id(db, "foo_raises")
        assert holder is not None, "the failing plugin should still be reported"
        assert holder.db_plugin.enabled is False
        assert "bad plugin settings" in (holder.db_plugin.load_error or "")


def test_record_escaped_load_error_tears_the_plugin_down_before_recording(
    install_path, session_local
):
    """A started plugin dropped from loaded_plugins must be stopped first.

    load_plugin registers the object and runs on_start before the savepoint
    releases, so a failure from the release leaves a live worker behind. Once
    the object is out of loaded_plugins nothing else reaches it, and shutdown()
    never stops the thread -- so the teardown has to happen before the branch
    that records the failure and stops looking at the plugin.
    """
    plugin_service = _service(install_path)
    plugin = _LifecycleSpy("orphan", enabled=True)
    plugin_service.loaded_plugins["orphan"] = plugin
    config = PluginInfo(id="orphan", name="orphan", main="main.py")

    # A real session, not a MagicMock: PluginHolder rejects a mock row, and the
    # method's own handler swallows that -- the test would pass with the
    # recording half never running.
    with session_local() as db:
        plugin_service._record_escaped_load_error(
            db, config, RuntimeError("savepoint release failed")
        )

        assert "orphan" not in plugin_service.loaded_plugins
        assert plugin.enabled is False
        assert plugin.calls == ["on_stop", "on_unload"]

        holder = plugin_service.get_by_id(db, "orphan")
        assert holder is not None, "the failure has to be recorded, not just logged"
        assert holder.db_plugin.enabled is False
        assert "savepoint release failed" in (holder.db_plugin.load_error or "")


def test_record_escaped_load_error_contains_a_db_failure_in_its_own_savepoint(
    install_path, session_local, caplog
):
    """The recovery path must not poison the transaction it is recovering in.

    load_plugins shares one session across every plugin, so an unguarded failed
    flush here deactivates the whole transaction: the plugins that already
    loaded lose their rows, every plugin after this one dies with
    PendingRollbackError against its own name, and startup()'s `with` block
    exits without committing *and without raising*, so the boot looks clean.
    """
    plugin_service = _service(install_path)
    plugin = _LifecycleSpy("poisoner", enabled=True)

    def on_stop(db):
        plugin.calls.append("on_stop")
        # A NOT NULL violation, standing in for the realistic shape: an on_stop
        # that writes a row referencing the plugins row the savepoint just
        # rolled back.
        db.add(db_models.Plugin(id="poisoner_task"))
        db.flush()

    plugin.on_stop = on_stop
    plugin_service.loaded_plugins["poisoner"] = plugin
    config = PluginInfo(id="poisoner", name="poisoner", main="main.py")

    with session_local() as db, caplog.at_level(logging.ERROR):
        db.add(
            db_models.Plugin(
                id="loaded_first",
                name="loaded_first",
                enabled=False,
                settings={},
                settings_initialized=False,
                info=config,
            )
        )
        db.flush()

        plugin_service._record_escaped_load_error(
            db, config, RuntimeError("savepoint release failed")
        )

        assert "Plugin poisoner failed to stop" in caplog.text
        assert db.is_active, "the caller's transaction must survive the recovery"
        # The plugin that had already loaded still has its row, and the failure
        # was still recorded despite the teardown blowing up. Both of these
        # raise PendingRollbackError if the bad flush was not savepointed.
        assert plugin_service.get_by_id(db, "loaded_first") is not None
        holder = plugin_service.get_by_id(db, "poisoner")
        assert holder is not None
        assert "savepoint release failed" in (holder.db_plugin.load_error or "")


def test_plugin_load_exception(install_path, session_local):
    plugin_service = _service(install_path)
    plugin_service.plugin_path = Path(install_path).parent / "test/plugin_install"
    plugin_service.startup()

    with session_local.begin() as db:
        plugin = plugin_service.get_by_id(db, "loadexceptionplugin")

        assert plugin is not None
        assert plugin.db_plugin.load_error == "This plugin is meant to fail to load."
        assert plugin.loaded_plugin is None
