import asyncio
import fnmatch
import importlib
import logging
import os
from datetime import datetime
from typing import List, Optional, Tuple, Union

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload, undefer

from empire.server.api.v2.plugin.plugin_dto import PluginExecutePostRequest
from empire.server.api.v2.plugin.plugin_task_dto import PluginTaskOrderOptions
from empire.server.api.v2.shared_dto import OrderDirection
from empire.server.core.config import empire_config
from empire.server.core.db import models
from empire.server.core.db.base import SessionLocal
from empire.server.core.db.models import AgentTaskStatus
from empire.server.core.exceptions import PluginValidationException
from empire.server.utils.option_util import validate_options

log = logging.getLogger(__name__)


class PluginService:
    def __init__(self, main_menu):
        self.main_menu = main_menu
        self.download_service = main_menu.downloadsv2
        self.loaded_plugins = {}

    def startup(self):
        """
        Called after plugin_service is initialized.
        This way plugin_service is fully initialized on MainMenu before plugins are loaded.
        """
        with SessionLocal.begin() as db:
            self.startup_plugins(db)
            self.autostart_plugins()

    def autostart_plugins(self):
        """
        Autorun plugin commands at server startup.
        """
        plugins = empire_config.yaml.get("plugins")
        if plugins:
            for plugin in plugins:
                use_plugin = self.loaded_plugins.get(plugin)
                if not use_plugin:
                    log.error(f"Plugin {plugin} not found.")
                    continue

                options = plugins[plugin]
                req = PluginExecutePostRequest(options=options)

                with SessionLocal.begin() as db:
                    results, err = self.execute_plugin(db, use_plugin, req, None)

                if results is False:
                    log.error(f"Plugin failed to run: {plugin}")
                else:
                    log.info(f"Plugin {plugin} ran successfully!")

    def startup_plugins(self, db: Session):
        """
        Load plugins at the start of Empire
        """
        plugin_path = f"{self.main_menu.installPath}/plugins/"
        log.info(f"Searching for plugins at {plugin_path}")

        # Import old v1 plugins (remove in 5.0)
        plugin_names = os.listdir(plugin_path)
        for plugin_name in plugin_names:
            if not plugin_name.lower().startswith(
                "__init__"
            ) and plugin_name.lower().endswith(".py"):
                file_path = os.path.join(plugin_path, plugin_name)
                self.load_plugin(plugin_name, file_path)

        for root, _dirs, files in os.walk(plugin_path):
            for filename in files:
                if not filename.lower().endswith(".plugin"):
                    continue

                file_path = os.path.join(root, filename)
                plugin_name = filename.split(".")[0]

                # don't load up any of the templates or examples
                if fnmatch.fnmatch(filename, "*template.plugin"):
                    continue
                elif fnmatch.fnmatch(filename, "*example.plugin"):
                    continue

                self.load_plugin(plugin_name, file_path)

    def load_plugin(self, plugin_name, file_path):
        """Given the name of a plugin and a menu object, load it into the menu"""
        # note the 'plugins' package so the loader can find our plugin
        loader = importlib.machinery.SourceFileLoader(plugin_name, file_path)
        module = loader.load_module()
        plugin_obj = module.Plugin(self.main_menu)

        for value in plugin_obj.options.values():
            if value.get("SuggestedValues") is None:
                value["SuggestedValues"] = []
            if value.get("Strict") is None:
                value["Strict"] = False

        self.loaded_plugins[plugin_name] = plugin_obj

    def execute_plugin(
        self,
        db: Session,
        plugin,
        plugin_req: PluginExecutePostRequest,
        user: Optional[models.User] = None,
    ) -> Tuple[Optional[Union[bool, str]], Optional[str]]:
        cleaned_options, err = validate_options(
            plugin.options, plugin_req.options, db, self.download_service
        )

        if err:
            raise PluginValidationException(err)

        try:
            # As of 5.2, plugins should now be executed with a user_id and db session
            res = plugin.execute(cleaned_options, db=db, user=user)
            if isinstance(res, tuple):
                return res
            return res, None
        except TypeError:
            log.warning(
                f"Plugin {plugin.info.get('Name')} does not support db session or user_id, falling back to old method"
            )
        except PluginValidationException as e:
            raise e
        except Exception as e:
            log.error(f"Plugin {plugin.info['Name']} failed to run: {e}", exc_info=True)
            return False, str(e)

        try:
            res = plugin.execute(cleaned_options)
            if isinstance(res, tuple):
                return res
            return res, None
        except PluginValidationException as e:
            raise e
        except Exception as e:
            log.error(f"Plugin {plugin.info['Name']} failed to run: {e}", exc_info=True)
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
    def get_tasks(
        db: Session,
        plugins: List[str] = None,
        users: List[int] = None,
        tags: List[str] = None,
        limit: int = -1,
        offset: int = 0,
        include_full_input: bool = False,
        include_output: bool = True,
        since: Optional[datetime] = None,
        order_by: PluginTaskOrderOptions = PluginTaskOrderOptions.id,
        order_direction: OrderDirection = OrderDirection.desc,
        status: Optional[AgentTaskStatus] = None,
        q: Optional[str] = None,
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
        results = list(map(lambda x: x[0], results))

        return results, total

    def shutdown(self):
        for plugin in self.loaded_plugins.values():
            plugin.shutdown()
