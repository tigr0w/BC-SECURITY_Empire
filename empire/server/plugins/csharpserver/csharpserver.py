import base64
import contextlib
import logging
import os
import socket
import subprocess
import time
from typing import override

from sqlalchemy.orm import Session

from empire.server.common import helpers
from empire.server.core.db import models
from empire.server.core.db.base import SessionLocal
from empire.server.core.db.models import PluginTaskStatus
from empire.server.core.plugins import BasePlugin

log = logging.getLogger(__name__)


class Plugin(BasePlugin):

    @override
    def on_load(self, db):
        self.csharpserver_proc = None
        self.thread = None
        self.tcp_ip = "127.0.0.1"
        self.tcp_port = 2012

    @override
    def on_start(self, db):
        compiler_path = (
            "/Empire-Compiler/EmpireCompiler/bin/Debug/net6.0/EmpireCompiler.dll"
        )
        server_dll = self.install_path + compiler_path

        # If dll hasn't been built yet
        if not os.path.exists(server_dll):
            csharp_cmd = ["dotnet", "build", self.install_path + "/csharp/"]
            self.csharpserverbuild_proc = subprocess.call(csharp_cmd)

        csharp_cmd = [
            "dotnet",
            self.install_path + compiler_path,
        ]

        self.csharpserver_proc = subprocess.Popen(
            csharp_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        self.thread = helpers.KThread(target=self.thread_csharp_responses, args=())
        self.thread.daemon = True
        self.thread.start()

        self.record_task(
            PluginTaskStatus.completed,
            "Starting Empire C# server",
            "Toggled Empire C# server on",
            db,
        )

    @override
    def on_stop(self, db):
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

        self.record_task(
            PluginTaskStatus.completed,
            "Stopping Empire C# server",
            "Toggled Empire C# server off",
            db,
        )

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
                with SessionLocal.begin() as db:
                    self.record_task(status, output, task_input, db)
                response_batch.clear()
                last_batch_time = time.time()

            if not response:
                if response_batch:
                    output = "\n".join(response_batch)
                    log.debug(output)
                    status = PluginTaskStatus.completed
                    with SessionLocal.begin() as db:
                        self.record_task(status, output, task_input, db)
                output = "Empire C# server output stream closed"
                status = PluginTaskStatus.error
                log.warning(output)
                with SessionLocal.begin() as db:
                    self.record_task(status, output, task_input, db)
                break

    def record_task(self, status, task_output, task_input, db: Session):
        plugin_task = models.PluginTask(
            plugin_id=self.info.name,
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
            self.send_socketio_message(recv_message)
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
            self.send_socketio_message(recv_message)
            file_name = "failed"
        s.close()

        return file_name
