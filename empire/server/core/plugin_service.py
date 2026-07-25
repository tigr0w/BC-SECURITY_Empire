import asyncio
import importlib
import logging
import shutil
import sys
import tarfile
import tempfile
import typing
import urllib.parse
import urllib.request
from pathlib import Path

import requests
import yaml
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.status import HTTP_200_OK

from empire.server.api.v2.plugin.plugin_dto import PluginExecutePostRequest
from empire.server.core.config import config_manager
from empire.server.core.config.config_manager import (
    PluginConfig,
    empire_config,
)
from empire.server.core.db import models
from empire.server.core.db.base import SessionLocal
from empire.server.core.db.models import PluginInfo
from empire.server.core.exceptions import (
    PluginExecutionException,
    PluginValidationException,
)
from empire.server.core.module_models import EmpireAuthor
from empire.server.core.plugins import BasePlugin
from empire.server.utils import git_util
from empire.server.utils.option_util import validate_options
from empire.server.utils.string_util import slugify

if typing.TYPE_CHECKING:
    from empire.server.common.empire import MainMenu

log = logging.getLogger(__name__)


class PluginHolder(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    loaded_plugin: BasePlugin | None
    db_plugin: models.Plugin | None


class PluginService:
    def __init__(self, main_menu: "MainMenu"):
        self.main_menu = main_menu
        self.download_service = main_menu.downloadsv2
        self.loaded_plugins = {}
        self.plugin_path = self.main_menu.install_path / "plugins"
        self.marketplace_path = config_manager.DATA_DIR / "plugins" / "marketplace"
        self.marketplace_path.mkdir(parents=True, exist_ok=True)

    def startup(self):
        """
        Called after plugin_service is initialized.
        This way plugin_service is fully initialized on MainMenu before plugins are loaded.
        """
        with SessionLocal.begin() as db:
            self.load_plugins(db)
            self.auto_execute_plugins(db)

    def update_plugin_enabled(
        self, db: Session, plugin_holder: PluginHolder, enabled: bool
    ):
        db_plugin = plugin_holder.db_plugin
        plugin = plugin_holder.loaded_plugin
        if plugin is None:
            raise PluginValidationException(
                f"Plugin {db_plugin.id} is not loaded and cannot be enabled or disabled"
            )
        # Checking both flags, not just the row: a failed on_stop leaves the
        # plugin stopped while the row still reads enabled, and the operator's
        # re-enable must not short-circuit into a no-op.
        if db_plugin.enabled == enabled and plugin.enabled == enabled:
            return

        # Flip before the hook: plugins guard background loops with
        # `while self.enabled`, so the thread has to see the new value already.
        previous = db_plugin.enabled
        db_plugin.enabled = enabled
        plugin.enabled = enabled
        try:
            if enabled:
                plugin.on_start(db)
            else:
                plugin.on_stop(db)
        except Exception:
            # The object stays False in both directions: on the disable path
            # the worker has already seen the stop, and execute_plugin gates on
            # this flag.
            db_plugin.enabled = previous
            plugin.enabled = False
            raise

        if enabled:
            # A successful start retires the last failure; otherwise the row
            # keeps a stale reason next to enabled: true.
            db_plugin.load_error = None

    def update_plugin_settings(
        self, db: Session, plugin_holder: PluginHolder, settings: dict
    ):
        """
        Will skip any options that are not editable.
        """
        return plugin_holder.loaded_plugin.set_settings(db, settings)

    def auto_execute_plugins(self, db):
        """
        Autorun plugin commands at server startup.
        """
        plugins = self.loaded_plugins
        for plugin_name, plugin in plugins.items():
            auto_execute = self._determine_auto_execute(plugin.info, empire_config)

            if auto_execute is None or auto_execute.enabled is False:
                continue

            req = PluginExecutePostRequest(options=auto_execute.options)
            try:
                results = self.execute_plugin(db, plugin, req, None)
            except (PluginValidationException, PluginExecutionException):
                log.exception(f"Plugin failed to run: {plugin_name}")
                continue

            if results is False:
                log.error(f"Plugin failed to run: {plugin_name}")
            else:
                log.info(f"Plugin {plugin_name} ran successfully!")

    def load_plugins(self, db: Session):
        """
        Load plugins at the start of Empire
        """
        log.info(f"Searching for plugins at {self.plugin_path}")

        for plugin_dir in self._list_plugin_directories():
            try:
                plugin_config = self._validate_plugin(plugin_dir)
            except Exception:
                # Not just PluginValidationException: a malformed plugin.yaml
                # surfaces as a yaml/pydantic error, and this runs from
                # MainMenu.__init__, so letting it escape takes the server down.
                log.exception(f"Failed to load plugin {plugin_dir.name}")
                continue

            # A savepoint, not a bare try: callers share one session, and a
            # failed flush deactivates the whole transaction -- every later
            # plugin would then die with PendingRollbackError under its own name.
            try:
                with db.begin_nested():
                    self.load_plugin(db, plugin_dir, plugin_config)
            except Exception as e:
                log.error(f"Failed to load plugin {plugin_config.id}", exc_info=True)
                self._record_escaped_load_error(db, plugin_config, e)

    def _record_escaped_load_error(
        self, db: Session, plugin_config: PluginInfo, error: Exception
    ):
        """Persist a load failure that escaped load_plugin's own handlers.

        Runs after the savepoint rolled back, so it writes in the caller's
        transaction, re-creating the row if load_plugin's insert went back with
        it. Best effort: this is an error path and must not stop the plugins
        after it from loading.
        """
        # Stop it before dropping it: once it is out of loaded_plugins nothing
        # reaches it again, and a worker on_start started outlives the server.
        plugin = self.loaded_plugins.pop(plugin_config.id, None)
        if plugin is not None:
            plugin.enabled = False
            # Savepointed like the load: these hooks are plugin-authored and can
            # flush into the caller's transaction.
            try:
                with db.begin_nested():
                    self._teardown_plugin(plugin_config.id, plugin, db)
            except Exception:
                log.error(f"Plugin {plugin_config.id} teardown failed", exc_info=True)

        # Savepointed too: this insert re-issues the row load_plugin just failed
        # to write, so it can fail the same way -- and unguarded that takes down
        # every plugin already loaded.
        try:
            with db.begin_nested():
                holder = self.get_by_id(db, plugin_config.id)
                if holder is not None:
                    holder.db_plugin.enabled = False
                    holder.db_plugin.load_error = str(error)
                else:
                    db.add(
                        self._new_plugin_row(
                            plugin_config, enabled=False, error=str(error)
                        )
                    )
        except Exception:
            log.error(
                f"Could not record the load failure for plugin {plugin_config.id}",
                exc_info=True,
            )

    @staticmethod
    def _new_plugin_row(
        plugin_config: PluginInfo,
        *,
        enabled: bool,
        version: str | None = None,
        error: str | None = None,
    ) -> models.Plugin:
        return models.Plugin(
            id=plugin_config.id,
            name=plugin_config.name,
            enabled=enabled,
            settings={},
            settings_initialized=False,
            info=plugin_config,
            installed_version=version,
            load_error=error,
        )

    def load_plugin(
        self,
        db: Session,
        plugin_dir: Path,
        plugin_config: PluginInfo,
        version: str | None = None,
    ):
        plugin_holder = self.get_by_id(db, plugin_config.id)

        if not plugin_holder:
            auto_start = self._determine_auto_start(plugin_config, empire_config)

            db_plugin = self._new_plugin_row(
                plugin_config, enabled=auto_start, version=version
            )
            db.add(db_plugin)
            db.flush()
        else:
            db_plugin = plugin_holder.db_plugin

        file_path = plugin_dir / plugin_config.main
        try:
            plugin_obj = self._create_plugin_obj(db, file_path, plugin_config)
        except Exception as e:
            db_plugin.enabled = False
            db_plugin.load_error = str(e)
            log.warning(f"Failed to load plugin {plugin_config.name}: {e}")
            return

        # Registered before anything else that can raise: __init__ already ran
        # on_load, and loaded_plugins is the only handle the failure paths have
        # for releasing what it registered.
        self.loaded_plugins[plugin_config.id] = plugin_obj

        if not db_plugin.settings_initialized:
            # Unguarded on purpose: on the load_plugins path the savepoint
            # rolls the row back and _record_escaped_load_error re-records the
            # failure; on the install path it surfaces to the API instead.
            plugin_obj.set_initial_options(db)
            db_plugin.settings_initialized = True

        # Set before the hook, same ordering as update_plugin_enabled.
        plugin_obj.enabled = db_plugin.enabled

        try:
            if db_plugin.enabled:
                plugin_obj.on_start(db)
        except Exception as e:
            log.error(
                f"Failed to start plugin {plugin_obj.info.name}: {e}", exc_info=True
            )
            plugin_obj.enabled = False
            db_plugin.enabled = False
            # Same column load_plugin already records an import failure to, so
            # a plugin that never started is not stored as a plain disable.
            db_plugin.load_error = f"Failed to start: {e}"
            return

        # Cleared only here: every failure path above records its own reason.
        db_plugin.load_error = None

    def _validate_and_load_plugin(
        self, db, temp_dir, subdir, version_name, registry_entry
    ):
        """Shared post-download logic: validate, merge config, load."""
        temp_dir = temp_dir / subdir if subdir else temp_dir
        plugin_dir, plugin_config = self._validate_temp_plugin(db, temp_dir)
        plugin_config = self._merge_plugin_config(plugin_config, registry_entry)
        self.load_plugin(db, plugin_dir, plugin_config, version_name)

    def _download_tar(self, tar_url):
        """Download and extract a tar archive. Returns the temp directory.

        Supports ``file://`` URIs (for local-path plugin installs) directly via
        the stdlib instead of mounting a third-party ``requests`` adapter.
        """
        temp_dir = (
            Path(tempfile.gettempdir()) / Path(tar_url.rsplit("/", maxsplit=1)[-1]).stem
        )
        parsed = urllib.parse.urlparse(tar_url)
        if parsed.scheme == "file":
            try:
                with (
                    Path(urllib.request.url2pathname(parsed.path)).open(
                        "rb"
                    ) as fileobj,
                    tarfile.open(fileobj=fileobj, mode="r|*") as tar,
                ):
                    # filter="data" guards against path traversal in the plugin archive.
                    tar.extractall(path=temp_dir, filter="data")
            except OSError as e:
                raise PluginValidationException(
                    f"Failed to download plugin: {e}"
                ) from e
            return temp_dir

        response = requests.get(tar_url, stream=True, timeout=30)
        if response.status_code != HTTP_200_OK:
            raise PluginValidationException(
                f"Failed to download plugin: {response.text}"
            )
        with tarfile.open(fileobj=response.raw, mode="r|*") as tar:
            # filter="data" guards against path traversal in the plugin archive.
            tar.extractall(path=temp_dir, filter="data")
        return temp_dir

    def install_plugin_from_git(  # noqa: PLR0913
        self,
        db: Session,
        git_url: str,
        subdir: str | None = None,
        ref: str | None = None,
        version_name: str | None = None,
        registry_entry: dict | None = None,
    ):
        temp_dir = git_util.clone_git_repo(git_url, ref)
        self._validate_and_load_plugin(
            db, temp_dir, subdir, version_name, registry_entry
        )

    def install_plugin_from_tar(
        self,
        db: Session,
        tar_url: str,
        subdir: str | None = None,
        version_name: str | None = None,
        registry_entry: dict | None = None,
    ):
        temp_dir = self._download_tar(tar_url)
        self._validate_and_load_plugin(
            db, temp_dir, subdir, version_name, registry_entry
        )

    @staticmethod
    def _merge_plugin_config(plugin_config, registry_entry):
        """
        If a plugin is installed from a registry, let the registry's author info
        take precedence over the plugin's own.

        `registry_entry` is one registry's entry for this plugin, not a whole
        registry document. The entry's `description` has nowhere to go --
        PluginInfo doesn't carry one -- so it stays a marketplace-only field.
        """
        if not registry_entry:
            return plugin_config

        # Raw YAML off the registry row, and PluginInfo doesn't validate on
        # assignment, so these would otherwise persist as bare dicts.
        authors = registry_entry.get("authors")
        if authors:
            plugin_config.authors = [EmpireAuthor.model_validate(a) for a in authors]

        return plugin_config

    def execute_plugin(
        self,
        db: Session,
        plugin,
        plugin_req: PluginExecutePostRequest,
        user: models.User | None = None,
    ) -> bool | str | None:
        if plugin.enabled is False:
            raise PluginValidationException("Plugin is not running")
        if not plugin.execution_enabled:
            raise PluginValidationException("Plugin execution is disabled")

        cleaned_options, err = validate_options(
            plugin.execution_options, plugin_req.options, db, self.download_service
        )

        if err:
            raise PluginValidationException(err)

        try:
            return plugin.execute(cleaned_options, db=db, user=user)
        except (PluginValidationException, PluginExecutionException):
            raise
        except Exception as e:
            log.error(f"Plugin {plugin.info.name} failed to run: {e}", exc_info=True)
            raise PluginExecutionException(str(e)) from e

    def plugin_socketio_message(self, plugin_name, msg):
        """
        Send socketio message to the socket address.
        Note: Use BasePlugin.send_socketio_message for easier use.
        """
        log.info(f"{plugin_name}: {msg}")
        if self.main_menu.socketio:
            try:  # https://stackoverflow.com/a/61331974/
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                loop.create_task(
                    self.main_menu.socketio.emit(
                        f"plugins/{plugin_name}/notifications",
                        {"message": msg, "plugin_name": plugin_name},
                    )
                )
            else:
                asyncio.run(
                    self.main_menu.socketio.emit(
                        f"plugins/{plugin_name}/notifications",
                        {"message": msg, "plugin_name": plugin_name},
                    )
                )

    def get_all(self, db):
        loaded_plugins = self.loaded_plugins
        db_plugins = db.scalars(select(models.Plugin)).all()

        ret = []
        for db_plugin in db_plugins:
            loaded_plugin = loaded_plugins.get(db_plugin.id)
            ret.append(PluginHolder(loaded_plugin=loaded_plugin, db_plugin=db_plugin))

        return ret

    def get_by_id(self, db: SessionLocal, uid: str) -> PluginHolder | None:
        loaded_plugin = self.loaded_plugins.get(uid)
        db_plugin = db.scalars(
            select(models.Plugin).where(models.Plugin.id == uid)
        ).first()

        if not db_plugin:
            return None

        return PluginHolder(loaded_plugin=loaded_plugin, db_plugin=db_plugin)

    @staticmethod
    def _teardown_plugin(plugin_id: str, plugin: BasePlugin, db: Session):
        """Run both teardown hooks, letting neither stop the other."""
        try:
            plugin.on_stop(db)
        except Exception:
            log.error(f"Plugin {plugin_id} failed to stop", exc_info=True)

        try:
            plugin.on_unload(db)
        except Exception:
            log.error(f"Plugin {plugin_id} failed to unload", exc_info=True)

    def shutdown(self):
        # list() because a plugin can mutate this dict, and the resulting
        # RuntimeError would come from the iterator, outside the guards below.
        for plugin_id, plugin in list(self.loaded_plugins.items()):
            # Before the session, not inside it: this is what stops a
            # `while self.enabled` worker, and it must happen even if the pool
            # is already gone.
            plugin.enabled = False

            # Guarded around the session, not just the hooks: opening it can
            # fail at shutdown, and its commit fires at block exit, outside the
            # inner handlers.
            try:
                with SessionLocal.begin() as db:
                    self._teardown_plugin(plugin_id, plugin, db)
            except Exception:
                log.error(f"Plugin {plugin_id} teardown failed", exc_info=True)

        # Keeps /plugins/reload honest: a plugin that then fails to reload is
        # reported as not loaded rather than as a live, torn-down object.
        self.loaded_plugins.clear()

    def _validate_plugin(self, plugin_dir: Path) -> PluginInfo:
        plugin_yaml = plugin_dir / "plugin.yaml"
        if not plugin_yaml.exists():
            raise PluginValidationException("plugin.yaml not found")

        plugin_config = PluginInfo(**yaml.safe_load(plugin_yaml.read_text()))
        plugin_config.id = slugify(plugin_config.name)
        readme = plugin_dir / "README.md"
        if readme.exists():
            plugin_config.readme = readme.read_text()
        plugin_file = plugin_dir / plugin_config.main

        if not plugin_file.is_file():
            raise PluginValidationException(
                f"Plugin {plugin_config.name} does not have a valid main file"
            )

        return plugin_config

    def _validate_temp_plugin(
        self, db: Session, temp_dir: Path
    ) -> tuple[Path, PluginInfo]:
        """Validate the plugin in the temp directory
        and move it to the plugin directory."""
        plugin_config = self._validate_plugin(temp_dir)

        if self.get_by_id(db, plugin_config.id):
            raise PluginValidationException("Plugin already exists")

        plugin_dir = self.marketplace_path / plugin_config.id
        shutil.move(temp_dir, plugin_dir)
        shutil.rmtree(plugin_dir / ".git", ignore_errors=True)

        return plugin_dir, plugin_config

    def _create_plugin_obj(self, db, file_path, plugin_config: PluginInfo):
        plugin_file_name = file_path.stem
        package_name = file_path.parent.name
        sys.path.append(str(file_path.parent.parent))

        spec = importlib.util.spec_from_file_location(
            f"{package_name}.{plugin_file_name}", str(file_path)
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        return module.Plugin(self.main_menu, plugin_config, db)

    @staticmethod
    def _determine_auto_start(plugin_config: PluginInfo, empire_config) -> bool:
        # Server Config -> Plugin Config (Default True)
        server_config = empire_config.plugins.get(plugin_config.id, PluginConfig())

        if server_config.auto_start is not None:
            return server_config.auto_start

        return plugin_config.auto_start

    @staticmethod
    def _determine_auto_execute(plugin_config, empire_config) -> PluginConfig | None:
        # Server Config -> Plugin Config -> Default (None)
        server_config = empire_config.plugins.get(plugin_config.id)

        if server_config is not None and server_config.auto_execute is not None:
            return server_config.auto_execute
        if plugin_config.auto_execute is not None:
            return plugin_config.auto_execute

        return None

    def _list_plugin_directories(self):
        def _ignore_plugin(plugin_dir):
            return (
                plugin_dir.name == "example"
                or not plugin_dir.is_dir()
                or plugin_dir.name.startswith(".")
                or plugin_dir.name.startswith("_")
            )

        main_dirs = [
            d
            for d in self.plugin_path.iterdir()
            if d.is_dir() and not _ignore_plugin(d)
        ]
        marketplace_dirs = [
            d
            for d in self.marketplace_path.iterdir()
            if d.is_dir() and not _ignore_plugin(d)
        ]

        return main_dirs + marketplace_dirs
