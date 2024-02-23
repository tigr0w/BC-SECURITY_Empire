""" Utilities and helpers and etc. for plugins """

import logging

from pydantic import BaseModel

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
    def __init__(self, main_menu, plugin_info: PluginInfo):
        # having these multiple messages should be helpful for debugging
        # user-reported errors (can narrow down where they happen)
        # any future init stuff goes here
        self.info = plugin_info
        try:
            # do custom user stuff
            self.onLoad()
            log.info(f"Initializing plugin: {self.info.name}")

            # Register functions to the main menu
            self.register(main_menu)

            # Give access to main menu
            self.main_menu = main_menu
        except Exception as e:
            if self.info.name:
                log.error(f"{self.info.name} failed to initialize: {e}")
            else:
                log.error(f"Error initializing plugin: {e}")

    def onLoad(self):
        """Things to do during init: meant to be overridden by
        the inheriting plugin."""
        pass

    def register(self, main_menu):
        """Any modifications made to the main menu are done here
        (meant to be overriden by child)"""
        pass
