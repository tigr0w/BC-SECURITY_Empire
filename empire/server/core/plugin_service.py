import asyncio
import importlib
import logging
import os
import typing
from datetime import datetime
from pathlib import Path

import yaml
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload, undefer

from empire.server.api.v2.plugin.plugin_dto import PluginExecutePostRequest
from empire.server.api.v2.plugin.plugin_task_dto import PluginTaskOrderOptions
from empire.server.api.v2.shared_dto import OrderDirection
from empire.server.core.config import empire_config
from empire.server.core.db import models
from empire.server.core.db.base import SessionLocal
from empire.server.core.db.models import AgentTaskStatus
from empire.server.core.exceptions import (
    PluginExecutionException,
    PluginValidationException,
)
from empire.server.core.plugins import PluginInfo
from empire.server.utils.option_util import validate_options

if typing.TYPE_CHECKING:
    from empire.server.common.empire import MainMenu

log = logging.getLogger(__name__)


class PluginService:
    def __init__(self, main_menu: "MainMenu"):
        self.main_menu = main_menu
        self.download_service = main_menu.downloadsv2
        self.loaded_plugins = {}

    def startup(self):
        """
        Called after plugin_service is initialized.
        This way plugin_service is fully initialized on MainMenu before plugins are loaded.
        """
        with SessionLocal.begin() as db:
            self.load_plugins(db)
            self.auto_execute_plugins(db)

    def get_plugin_db(self, db: Session, plugin_id: str):
        return db.query(models.Plugin).filter(models.Plugin.id == plugin_id).first()

    def update_plugin_enabled(self, db: Session, plugin, enabled: bool):
        db_plugin = self.get_plugin_db(db, plugin.info.name)
        if db_plugin.enabled == enabled:
            return
        if enabled:
            plugin.on_start(db)
            db_plugin.enabled = True
            plugin.enabled = True
        else:
            plugin.on_stop(db)
            db_plugin.enabled = False
            plugin.enabled = False

    def update_plugin_settings(self, db: Session, plugin, settings: dict):
        """
        Will skip any options that are not editable.
        """
        cleaned_options, err = validate_options(
            plugin.settings_options, settings, db, self.download_service
        )

        if err:
            raise PluginValidationException(err)

        # Add the uneditable settings back to the dict.
        current_settings = plugin.current_settings(db)
        cleaned_options = {**current_settings, **cleaned_options}

        db_plugin = self.get_plugin_db(db, plugin.info.name)
        db_plugin.settings = cleaned_options

        return cleaned_options

    def auto_execute_plugins(self, db):
        """
        Autorun plugin commands at server startup.
        """
        plugins = empire_config.yaml.get("plugins", {})

        for plugin_name, options in plugins.items():
            use_plugin = self.loaded_plugins.get(plugin_name)
            if not use_plugin:
                log.error(f"Plugin {plugin_name} not found.")
                continue

            req = PluginExecutePostRequest(options=options)

            results, err = self.execute_plugin(db, use_plugin, req, None)

            if results is False:
                log.error(f"Plugin failed to run: {plugin_name}")
            else:
                log.info(f"Plugin {plugin_name} ran successfully!")

    def load_plugins(self, db: Session):
        """
        Load plugins at the start of Empire
        """
        plugin_path = f"{self.main_menu.installPath}/plugins/"
        log.info(f"Searching for plugins at {plugin_path}")

        for directory in os.listdir(plugin_path):
            plugin_dir = Path(plugin_path) / directory

            if (
                directory == "example"
                or not plugin_dir.is_dir()
                or plugin_dir.name.startswith(".")
                or plugin_dir.name.startswith("_")
            ):
                continue

            plugin_yaml = plugin_dir / "plugin.yaml"

            if not plugin_yaml.exists():
                log.warning(f"Plugin {plugin_dir.name} does not have a plugin.yaml")
                continue

            plugin_config = yaml.safe_load(plugin_yaml.read_text())
            plugin_main = plugin_config.get("main")
            plugin_file = plugin_dir / plugin_main

            if not plugin_file.is_file():
                log.warning(f"Plugin {plugin_dir.name} does not have a valid main file")
                continue

            try:
                self.load_plugin(db, plugin_file, plugin_config)
            except Exception as e:
                log.error(
                    f"Failed to load plugin {plugin_file.name}: {e}", exc_info=True
                )

    def load_plugin(self, db: Session, file_path: Path, plugin_config: dict):
        """Given the name of a plugin and a menu object, load it into the menu"""
        plugin_obj = self._create_plugin_obj(db, file_path, plugin_config)

        self.loaded_plugins[plugin_obj.info.name] = plugin_obj
        db_plugin = self.get_plugin_db(db, plugin_obj.info.name)

        if not db_plugin:
            auto_start = self._determine_auto_start(plugin_obj, empire_config)

            db_plugin = models.Plugin(
                id=plugin_obj.info.name,
                name=plugin_obj.info.name,
                enabled=auto_start,
                settings={},
            )
            db.add(db_plugin)
            db.flush()
            plugin_obj.set_initial_options(db)

        try:
            if db_plugin.enabled:
                plugin_obj.on_start(db)
        except Exception as e:
            log.error(
                f"Failed to start plugin {plugin_obj.info.name}: {e}", exc_info=True
            )
            plugin_obj.enabled = False
            db_plugin.enabled = False

        plugin_obj.enabled = db_plugin.enabled

    def _create_plugin_obj(self, db, file_path, plugin_config):
        plugin_file_name = file_path.name.removesuffix(".py")
        plugin_info = PluginInfo(**plugin_config)
        loader = importlib.machinery.SourceFileLoader(plugin_file_name, str(file_path))
        module = loader.load_module()
        return module.Plugin(self.main_menu, plugin_info, db)

    @staticmethod
    def _determine_auto_start(plugin_obj, empire_config) -> bool:
        # Server Config -> Plugin Config -> Default (True)
        # Every plugin will auto start.
        # A subsequent PR will add the configuration.
        return True

    def execute_plugin(
        self,
        db: Session,
        plugin,
        plugin_req: PluginExecutePostRequest,
        user: models.User | None = None,
    ) -> tuple[bool | str | None, str | None]:
        # Since some plugins are enabled/disabled via execution, we still have to allow
        # the execution to continue even if the plugin is disabled.
        # In a subsequent PR, this will be uncommented.
        # if plugin.enabled is False:
        #     raise PluginValidationException("Plugin is not running")

        cleaned_options, err = validate_options(
            plugin.execution_options, plugin_req.options, db, self.download_service
        )

        if err:
            raise PluginValidationException(err)

        try:
            res = plugin.execute(cleaned_options, db=db, user=user)
            # Tuple is deprecated. Will be removed in 7.x
            if isinstance(res, tuple):
                return res
            return res, None
        except (PluginValidationException, PluginExecutionException) as e:
            raise e
        except Exception as e:
            log.error(f"Plugin {plugin.info.name} failed to run: {e}", exc_info=True)
            return False, str(e)

    def plugin_socketio_message(self, plugin_name, msg):
        """
        Send socketio message to the socket address
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

    def get_all(self):
        return self.loaded_plugins

    def get_by_id(self, uid: str):
        return self.loaded_plugins.get(uid)

    def get_task(self, db: SessionLocal, plugin_id: str, task_id: int):
        plugin = self.get_by_id(plugin_id)
        if plugin:
            task = (
                db.query(models.PluginTask)
                .filter(models.PluginTask.id == task_id)
                .first()
            )
            if task:
                return task

        return None

    @staticmethod
    def get_tasks(  # noqa: PLR0913 PLR0912
        db: Session,
        plugins: list[str] | None = None,
        users: list[int] | None = None,
        tags: list[str] | None = None,
        limit: int = -1,
        offset: int = 0,
        include_full_input: bool = False,
        include_output: bool = True,
        since: datetime | None = None,
        order_by: PluginTaskOrderOptions = PluginTaskOrderOptions.id,
        order_direction: OrderDirection = OrderDirection.desc,
        status: AgentTaskStatus | None = None,
        q: str | None = None,
    ):
        query = db.query(
            models.PluginTask, func.count(models.PluginTask.id).over().label("total")
        )

        if plugins:
            query = query.filter(models.PluginTask.plugin_id.in_(plugins))

        if users:
            user_filters = [models.PluginTask.user_id.in_(users)]
            if 0 in users:
                user_filters.append(models.PluginTask.user_id.is_(None))
            query = query.filter(or_(*user_filters))

        if tags:
            tags_split = [tag.split(":", 1) for tag in tags]
            query = query.join(models.PluginTask.tags).filter(
                and_(
                    models.Tag.name.in_([tag[0] for tag in tags_split]),
                    models.Tag.value.in_([tag[1] for tag in tags_split]),
                )
            )

        query_options = [
            joinedload(models.PluginTask.user),
        ]

        if include_full_input:
            query_options.append(undefer(models.PluginTask.input_full))
        if include_output:
            query_options.append(undefer(models.PluginTask.output))
        query = query.options(*query_options)

        if since:
            query = query.filter(models.PluginTask.updated_at > since)

        if status:
            query = query.filter(models.AgentTask.status == status)

        if q:
            query = query.filter(
                or_(
                    models.PluginTask.input.like(f"%{q}%"),
                    models.PluginTask.output.like(f"%{q}%"),
                )
            )

        if order_by == PluginTaskOrderOptions.status:
            order_by_prop = models.PluginTask.status
        elif order_by == PluginTaskOrderOptions.updated_at:
            order_by_prop = models.PluginTask.updated_at
        elif order_by == PluginTaskOrderOptions.plugin:
            order_by_prop = models.PluginTask.plugin_id
        else:
            order_by_prop = models.PluginTask.id

        if order_direction == OrderDirection.asc:
            query = query.order_by(order_by_prop.asc())
        else:
            query = query.order_by(order_by_prop.desc())

        if limit > 0:
            query = query.limit(limit).offset(offset)

        results = query.all()

        total = 0 if len(results) == 0 else results[0].total
        results = [x[0] for x in results]

        return results, total

    def shutdown(self):
        with SessionLocal.begin() as db:
            for plugin in self.loaded_plugins.values():
                plugin.on_stop(db)
                plugin.on_unload(db)
