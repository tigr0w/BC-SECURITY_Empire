import logging
from typing import Any

from pydantic import BaseModel

from empire.server.core.config import PluginAutoExecuteConfig
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
    auto_start: bool = True
    auto_execute: PluginAutoExecuteConfig | None = None


class BasePlugin:
    def __init__(self, main_menu, plugin_info: PluginInfo, db: SessionLocal):
        self.main_menu = main_menu
        self.info: PluginInfo = plugin_info

        log.info(f"Initializing plugin: {self.info.name}")

        self.enabled: bool = False
        self.execution_enabled: bool = True
        self.install_path: str = self.main_menu.installPath
        self.execution_options: dict = {}
        self.settings_options: dict = {}

        try:
            self.on_load(db)
            self._set_options_defaults()
        except Exception as e:
            if self.info.name:
                log.error(f"{self.info.name} failed to initialize: {e}")
            else:
                log.error(f"Error initializing plugin: {e}")

    def _set_options_defaults(self):
        for value in self.execution_options.values():
            if value.get("SuggestedValues") is None:
                value["SuggestedValues"] = []
            if value.get("Strict") is None:
                value["Strict"] = False

        for value in self.settings_options.values():
            if value.get("SuggestedValues") is None:
                value["SuggestedValues"] = []
            if value.get("Strict") is None:
                value["Strict"] = False

    def set_initial_options(self, db):
        """
        Set the initial uneditable options for the plugin, based on
        the state_options. This is only used to initialize the fields in
        the database. Future updates should be done through the state functions
        or plugin_service.
        """
        settings = {}
        for key, value in self.settings_options.items():
            settings[key] = value["Value"]

        self.set_settings(db, settings)

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

    def current_settings(self, db) -> dict[str, Any]:
        return self.get_db_plugin(db).settings

    def current_internal_state(self, db) -> dict[str, Any]:
        return self.get_db_plugin(db).internal_state

    def set_settings(self, db, settings: dict[str, Any]):
        db_plugin = self.get_db_plugin(db)
        db_plugin.settings = settings
        db.flush()

    def set_internal_state(self, db, state: dict[str, Any]):
        db_plugin = self.get_db_plugin(db)
        db_plugin.internal_state = state
        db.flush()

    def set_settings_option(self, db, key, value):
        settings = self.current_settings(db)
        settings[key] = value
        self.set_settings(db, settings)

    def set_internal_state_option(self, db, key, value):
        state = self.current_internal_state(db)
        state[key] = value
        self.set_internal_state(db, state)

    def send_socketio_message(self, message):
        """Send a message to the socketio server"""
        self.main_menu.plugin_service.plugin_socketio_message(self.info.name, message)
