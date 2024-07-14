import contextlib
import logging

import websockify

import empire.server.common.helpers as helpers
from empire.server.core.plugin_service import PluginService
from empire.server.core.plugins import BasePlugin

log = logging.getLogger(__name__)


class Plugin(BasePlugin):
    def onLoad(self):
        self.main_menu = None
        self.csharpserver_proc = None

        self.options = {
            "SourceHost": {
                "Description": "Address of the source host.",
                "Required": True,
                "Value": "0.0.0.0",
            },
            "SourcePort": {
                "Description": "Port on source host.",
                "Required": True,
                "Value": "5910",
            },
            "TargetHost": {
                "Description": "Address of the target host.",
                "Required": True,
                "Value": "",
            },
            "TargetPort": {
                "Description": "Port on target host.",
                "Required": True,
                "Value": "5900",
            },
            "Status": {
                "Description": "Start/stop the Empire C# server.",
                "Required": True,
                "Value": "start",
                "SuggestedValues": ["start", "stop"],
                "Strict": True,
            },
        }

    def execute(self, command):
        # This is for parsing commands through the api
        try:
            self.websockify_proc = None
            # essentially switches to parse the proper command to execute
            self.status = command["Status"]
            results = self.do_websockify(command)
            return results
        except Exception as e:
            log.error(e)
            return False, f"[!] {e}"

    def get_commands(self):
        return self.commands

    def register(self, main_menu):
        """
        any modifications to the main_menu go here - e.g.
        registering functions to be run by user commands
        """
        self.installPath = main_menu.installPath
        self.main_menu = main_menu
        self.plugin_service: PluginService = main_menu.pluginsv2

    def do_websockify(self, command):
        """
        Check if the Empire C# server is already running.
        """
        if self.websockify_proc:
            self.enabled = True
        else:
            self.enabled = False

        if self.status == "status":
            if self.enabled:
                return "[+] Websockify server is currently running"
            else:
                return "[!] Websockify server is currently stopped"

        elif self.status == "stop":
            if self.enabled:
                self.shutdown()
                return "[!] Stopped Websockify server"
            else:
                return "[!] Websockify server is already stopped"

        elif self.status == "start":
            source_host = command["SourceHost"]
            source_port = int(command["SourcePort"])
            target_host = command["TargetHost"]
            target_port = int(command["TargetPort"])

            server = websockify.LibProxyServer(
                target_host=target_host,
                target_port=target_port,
                listen_host=source_host,
                listen_port=source_port,
            )

            self.websockify_proc = helpers.KThread(target=server.serve_forever)
            self.websockify_proc.daemon = True
            self.websockify_proc.start()
            return "[+] Websockify server successfully started"

    def shutdown(self):
        with contextlib.suppress(Exception):
            self.websockify_proc.kill()
        return
