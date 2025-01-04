import contextlib
import logging
from typing import override

import websockify

from empire.server.common import helpers
from empire.server.core.plugins import BasePlugin

log = logging.getLogger(__name__)


class Plugin(BasePlugin):
    @override
    def on_load(self, db):
        self.execution_enabled = False
        self.csharpserver_proc = None
        self.settings_options = {
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
        }

    @override
    def on_start(self, db):
        current_settings = self.current_settings(db)
        source_host = current_settings["SourceHost"]
        source_port = int(current_settings["SourcePort"])
        target_host = current_settings["TargetHost"]
        target_port = int(current_settings["TargetPort"])

        server = websockify.LibProxyServer(
            target_host=target_host,
            target_port=target_port,
            listen_host=source_host,
            listen_port=source_port,
        )

        self.websockify_proc = helpers.KThread(target=server.serve_forever)
        self.websockify_proc.daemon = True
        self.websockify_proc.start()

    @override
    def on_stop(self, db):
        with contextlib.suppress(Exception):
            self.websockify_proc.kill()
