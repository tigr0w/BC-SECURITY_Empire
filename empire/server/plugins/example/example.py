""" An example of a plugin. """

import logging

from empire.server.core.plugins import BasePlugin

# Relative imports don't work in plugins right now.
# from . import example_helpers
# example_helpers.this_is_an_example_function()
from empire.server.plugins.example import example_helpers

example_helpers.this_is_an_example_function()

log = logging.getLogger(__name__)

# anything you simply write out (like a script) will run immediately when the
# module is imported (before the class is instantiated)
log.info("Hello from your new plugin!")


# this class MUST be named Plugin
class Plugin(BasePlugin):
    def onLoad(self):
        """
        Any custom loading behavior - called by init, so any
        behavior you'd normally put in __init__ goes here
        """
        log.info("Custom loading behavior happens now.")

        # you can store data here that will persist until the plugin
        # is unloaded (i.e. Empire closes)
        self.calledTimes = 0

        # Any options needed by the plugin, settable during runtime
        self.options = {
            # Format:
            #   value_name : {description, required, default_value}
            "Status": {
                # The 'Agent' option is the only one that MUST be in a module
                "Description": "Example Status update",
                "Required": True,
                "Value": "start",
            },
            "Message": {
                "Description": "Message to print",
                "Required": True,
                "Value": "test",
            },
        }

    def execute(self, command, **kwargs):
        """
        Parses commands from the API
        """
        try:
            results = self.do_test(command)
            return results
        except Exception:
            return False

    def register(self, main_menu):
        """
        Any modifications to the main_menu go here - e.g.
        registering functions to be run by user commands
        """
        self.installPath = main_menu.installPath
        self.main_menu = main_menu

    def do_test(self, command):
        """
        An example of a plugin function.
        Usage: test <start|stop> <message>
        """
        log.info("This is executed from a plugin!")

        self.status = command["Status"]

        if self.status == "start":
            self.calledTimes += 1
            log.info(f"This function has been called {self.calledTimes} times.")
            log.info("Message: " + command["Message"])

        else:
            log.info("Usage: example <start|stop> <message>")

    def shutdown(self):
        """
        Kills additional processes that were spawned
        """
        # If the plugin spawns a process provide a shutdown method for when Empire exits else leave it as pass
        pass
