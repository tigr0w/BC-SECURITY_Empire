""" Utilities and helpers and etc. for plugins """
import logging
from builtins import object

log = logging.getLogger(__name__)


class Plugin(object):
    # to be overwritten by child
    description = "This is a description of this plugin."

    def __init__(self, mainMenu):
        # having these multiple messages should be helpful for debugging
        # user-reported errors (can narrow down where they happen)
        log.info("Initializing plugin...")
        # any future init stuff goes here

        log.info("Doing custom initialization...")
        # do custom user stuff
        self.onLoad()

        # now that everything is loaded, register functions and etc. onto the main menu
        log.info("Registering plugin with menu...")
        self.register(mainMenu)

        # Give access to main menu
        self.mainMenu = mainMenu

    def onLoad(self):
        """Things to do during init: meant to be overridden by
        the inheriting plugin."""
        pass

    def register(self, mainMenu):
        """Any modifications made to the main menu are done here
        (meant to be overriden by child)"""
        pass
