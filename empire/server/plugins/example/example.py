""" An example of a plugin. """

import logging

from empire.server.common.plugins import Plugin

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
class Plugin(Plugin):
    def onLoad(self):
        """
        Any custom loading behavior - called by init, so any
        behavior you'd normally put in __init__ goes here
        """
        log.info("Custom loading behavior happens now.")

        # you can store data here that will persist until the plugin
        # is unloaded (i.e. Empire closes)
        self.calledTimes = 0

        self.info = {
            # Plugin Name
            "Name": "example",
            # List of one or more authors for the plugin
            "Authors": [
                {
                    "Name": "Your Name",
                    "Handle": "@yourname",
                    "Link": "https://github.com/yourname",
                }
            ],
            # More verbose multi-line description of the plugin
            "Description": ("description line 1 " "description line 2"),
            # Software and tools that from the MITRE ATT&CK framework (https://attack.mitre.org/software/)
            "Software": "SXXXX",
            # Techniques that from the MITRE ATT&CK framework (https://attack.mitre.org/techniques/enterprise/)
            "Techniques": ["TXXXX", "TXXXX"],
            # List of any references/other comments
            "Comments": ["comment", "http://link/"],
        }

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

    def execute(self, command):
        """
        Parses commands from the API
        """
        try:
            results = self.do_test(command)
            return results
        except Exception:
            return False

    def register(self, mainMenu):
        """
        Any modifications to the mainMenu go here - e.g.
        registering functions to be run by user commands
        """
        self.installPath = mainMenu.installPath
        self.main_menu = mainMenu

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
