import logging

from pydantic import BaseModel

from empire.server.core.db import models
from empire.server.core.db.base import SessionLocal
from empire.server.core.module_models import EmpireAuthor

log = logging.getLogger(__name__)


class PluginInfo(BaseModel):
    name: str
    authors: list[EmpireAuthor] = []
    description: str | None = ""
    software: str | None = ""
    techniques: list[str] | None = []
    tactics: list[str] | None = []
    comments: list[str] | None = []


class BasePlugin:
    def __init__(self, main_menu, plugin_info: PluginInfo, db: SessionLocal):
        self.main_menu = main_menu
        self.info: PluginInfo = plugin_info

        log.info(f"Initializing plugin: {self.info.name}")

        self.enabled: bool = False
        self.install_path: str = self.main_menu.installPath
        self.options: dict = {}

        try:
            self.on_load(db)
            self._set_options_defaults()
        except Exception as e:
            if self.info.name:
                log.error(f"{self.info.name} failed to initialize: {e}")
            else:
                log.error(f"Error initializing plugin: {e}")

    def _set_options_defaults(self):
        for value in self.options.values():
            if value.get("SuggestedValues") is None:
                value["SuggestedValues"] = []
            if value.get("Strict") is None:
                value["Strict"] = False

    def on_load(self, db):
        """Things to do during init: meant to be overridden by
        the inheriting plugin."""
        pass

    def on_unload(self, db):
        """Things to do when the plugin is unloaded: meant to be overridden by
        the inheriting plugin."""
        pass

    def on_start(self, db):
        """Things to do when the plugin is started: meant to be overridden by
        the inheriting plugin."""
        pass

    def on_stop(self, db):
        """Things to do when the plugin is stopped: meant to be overridden by
        the inheriting plugin."""
        pass

    def execute(self, command, **kwargs):
        """Execute a command: meant to be overridden by the inheriting plugin."""
        pass

    def get_db_plugin(self, db) -> models.Plugin | None:
        return (
            db.query(models.Plugin).filter(models.Plugin.id == self.info.name).first()
        )

    def send_socketio_message(self, message):
        """Send a message to the socketio server"""
        self.main_menu.plugin_service.plugin_socketio_message(self.info.name, message)
