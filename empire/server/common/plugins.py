""" Utilities and helpers and etc. for plugins """
import logging

log = logging.getLogger(__name__)


class Plugin:
    # to be overwritten by child
    def __init__(self, mainMenu):
        # having these multiple messages should be helpful for debugging
        # user-reported errors (can narrow down where they happen)
        # any future init stuff goes here
        try:
            # do custom user stuff
            self.onLoad()
            log.info(f"Initializing plugin: {self.info['Name']}")

            # Register functions to the main menu
            self.register(mainMenu)

            # Give access to main menu
            self.mainMenu = mainMenu
        except Exception as e:
            if self.info["Name"]:
                log.error(f"{self.info['Name']} failed to initialize: {e}")
            else:
                log.error(f"Error initializing plugin: {e}")

    def onLoad(self):
        """Things to do during init: meant to be overridden by
        the inheriting plugin."""
        pass

    def register(self, mainMenu):
        """Any modifications made to the main menu are done here
        (meant to be overriden by child)"""
        pass
