import base64
import contextlib
import logging
import os
import socket
import subprocess
import time

from empire.server.common import helpers
from empire.server.common.empire import MainMenu
from empire.server.common.plugins import BasePlugin
from empire.server.core.db import models
from empire.server.core.db.base import SessionLocal
from empire.server.core.db.models import PluginTaskStatus
from empire.server.core.plugin_service import PluginService

log = logging.getLogger(__name__)


class Plugin(BasePlugin):
    def onLoad(self):
        self.info = {
            "Name": "csharpserver",
            "Authors": [
                {
                    "Name": "Anthony Rose",
                    "Handle": "@Cx01N",
                    "Link": "https://twitter.com/Cx01N_",
                }
            ],
            "Description": ("Empire C# server for agents."),
            "Software": "",
            "Techniques": [""],
            "Comments": [],
        }

        self.options = {
            "status": {
                "Description": "Start/stop the Empire C# server.",
                "Required": True,
                "Value": "start",
                "SuggestedValues": ["start", "stop"],
                "Strict": True,
            }
        }

        self.csharpserver_proc = None
        self.thread = None
        self.tcp_ip = "127.0.0.1"
        self.tcp_port = 2012
        self.status = "OFF"

    def execute(self, command, **kwargs):
        db = kwargs["db"]
        if command["status"] == "start":
            input = "Starting Empire C# server..."
        else:
            input = "Stopping Empire C# server..."

        plugin_task = models.PluginTask(
            plugin_id=self.info["Name"],
            input=input,
            input_full=input,
            user_id=1,
            status=PluginTaskStatus.completed,
        )
        output = self.toggle_csharpserver(command)
        plugin_task.output = output
        db.add(plugin_task)
        db.flush()

    def register(self, main_menu: MainMenu):
        self.installPath = main_menu.installPath
        self.main_menu = main_menu
        self.plugin_service: PluginService = main_menu.pluginsv2

    def toggle_csharpserver(self, command):
        self.start = command["status"]

        if not self.csharpserver_proc or self.csharpserver_proc.poll():
            self.status = "OFF"
        else:
            self.status = "ON"

        if self.start == "stop":
            if self.status == "ON":
                self.shutdown()
                self.status = "OFF"
                return "[*] Stopping Empire C# server"
            else:
                return "[!] Empire C# server is already stopped"

        elif self.start == "start":
            if self.status == "OFF":
                server_dll = (
                    self.installPath
                    + "/csharp/Covenant/bin/Debug/net6.0/EmpireCompiler.dll"
                )
                if not os.path.exists(server_dll):
                    csharp_cmd = ["dotnet", "build", self.installPath + "/csharp/"]
                    self.csharpserverbuild_proc = subprocess.call(csharp_cmd)

                csharp_cmd = [
                    "dotnet",
                    self.installPath
                    + "/csharp/Covenant/bin/Debug/net6.0/EmpireCompiler.dll",
                ]

                self.csharpserver_proc = subprocess.Popen(
                    csharp_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )

                self.thread = helpers.KThread(
                    target=self.thread_csharp_responses, args=()
                )
                self.thread.daemon = True
                self.thread.start()

                self.status = "ON"

                return "[*] Starting Empire C# server"
            else:
                return "[!] Empire C# server is already started"

    def thread_csharp_responses(self):
        task_input = "Collecting Empire C# server output stream..."
        batch_timeout = 5  # seconds
        response_batch = []
        last_batch_time = time.time()

        while True:
            response = self.csharpserver_proc.stdout.readline().rstrip()
            if response:
                response_batch.append(response.decode("UTF-8"))

            if (time.time() - last_batch_time) >= batch_timeout:
                output = "\n".join(response_batch)
                log.debug(output)
                status = PluginTaskStatus.completed
                self.record_task(status, output, task_input)
                response_batch.clear()
                last_batch_time = time.time()

            if not response:
                if response_batch:
                    output = "\n".join(response_batch)
                    log.debug(output)
                    status = PluginTaskStatus.completed
                    self.record_task(status, output, task_input)
                output = "Empire C# server output stream closed"
                status = PluginTaskStatus.error
                log.warning(output)
                self.record_task(status, output, task_input)
                break

    def record_task(self, status, task_output, task_input):
        with SessionLocal.begin() as db:
            plugin_task = models.PluginTask(
                plugin_id=self.info["Name"],
                input=task_input,
                input_full=task_input,
                user_id=1,
                status=status,
            )

            plugin_task.output = task_output
            db.add(plugin_task)
            db.flush()

    def do_send_message(self, compiler_yaml, task_name, confuse=False):
        bytes_yaml = compiler_yaml.encode("UTF-8")
        b64_yaml = base64.b64encode(bytes_yaml)
        bytes_task_name = task_name.encode("UTF-8")
        b64_task_name = base64.b64encode(bytes_task_name)

        bytes_confuse = b"true" if confuse else b"false"
        b64_confuse = base64.b64encode(bytes_confuse)

        deliminator = b","
        message = b64_task_name + deliminator + b64_confuse + deliminator + b64_yaml
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.tcp_ip, self.tcp_port))
        s.send(message)

        recv_message = s.recv(1024)
        recv_message = recv_message.decode("ascii")
        if recv_message.startswith("FileName:"):
            file_name = recv_message.split(":")[1]
        else:
            self.plugin_service.plugin_socketio_message(
                self.info["Name"], ("[*] " + recv_message)
            )
            file_name = "failed"
        s.close()

        return file_name

    def do_send_stager(self, stager, task_name, confuse=False):
        bytes_yaml = stager.encode("UTF-8")
        b64_yaml = base64.b64encode(bytes_yaml)
        bytes_task_name = task_name.encode("UTF-8")
        b64_task_name = base64.b64encode(bytes_task_name)

        bytes_confuse = b"true" if confuse else b"false"
        b64_confuse = base64.b64encode(bytes_confuse)

        deliminator = b","
        message = b64_task_name + deliminator + b64_confuse + deliminator + b64_yaml
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.tcp_ip, self.tcp_port))
        s.send(message)

        recv_message = s.recv(1024)
        recv_message = recv_message.decode("ascii")
        if recv_message.startswith("FileName:"):
            file_name = recv_message.split(":")[1]
        else:
            self.plugin_service.plugin_socketio_message(
                self.info["Name"], ("[*] " + recv_message)
            )
            file_name = "failed"
        s.close()

        return file_name

    def shutdown(self):
        with contextlib.suppress(Exception):
            b64_yaml = base64.b64encode(b"dummy data")
            b64_confuse = base64.b64encode(b"false")
            b64_task_name = base64.b64encode(b"close")
            deliminator = b","
            message = b64_task_name + deliminator + b64_confuse + deliminator + b64_yaml
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((self.tcp_ip, self.tcp_port))
            s.send(message)
            s.close()
            self.csharpserverbuild_proc.kill()
            self.csharpserver_proc.kill()
            self.thread.kill()
