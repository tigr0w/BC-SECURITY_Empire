"""

The main controller class for Empire.

This is what's launched from ./empire.
Contains the Main, Listener, Agents, Agent, and Module
menu loops.

"""
from __future__ import absolute_import

import asyncio
import logging
import time
from socket import SocketIO
from typing import Optional

# Empire imports
from empire.server.common import hooks_internal
from empire.server.common.config import empire_config
from empire.server.utils import data_util
from empire.server.v2.core.agent_file_service import AgentFileService
from empire.server.v2.core.agent_service import AgentService
from empire.server.v2.core.agent_task_service import AgentTaskService
from empire.server.v2.core.bypass_service import BypassService
from empire.server.v2.core.credential_service import CredentialService
from empire.server.v2.core.download_service import DownloadService
from empire.server.v2.core.host_process_service import HostProcessService
from empire.server.v2.core.host_service import HostService
from empire.server.v2.core.listener_service import ListenerService
from empire.server.v2.core.listener_template_service import ListenerTemplateService
from empire.server.v2.core.module_service import ModuleService
from empire.server.v2.core.obfuscation_service import ObfuscationService
from empire.server.v2.core.plugin_service import PluginService
from empire.server.v2.core.profile_service import ProfileService
from empire.server.v2.core.stager_service import StagerService
from empire.server.v2.core.stager_template_service import StagerTemplateService
from empire.server.v2.core.user_service import UserService

from . import agents, credentials, listeners, stagers

VERSION = "5.0.0-alpha1 BC Security Fork"

log = logging.getLogger(__name__)


class MainMenu(object):
    """
    The main class used by Empire to drive the 'main' menu
    displayed when Empire starts.
    """

    def __init__(self, args=None):
        time.sleep(1)

        # pull out some common configuration information
        (
            self.isroot,
            self.installPath,
            self.ipWhiteList,
            self.ipBlackList,
        ) = data_util.get_config("rootuser, install_path,ip_whitelist,ip_blacklist")

        # parse/handle any passed command line arguments
        self.args = args

        self.socketio: Optional[SocketIO] = None

        self.agents = agents.Agents(self, args=args)
        self.credentials = credentials.Credentials(self, args=args)
        self.stagers = stagers.Stagers(self, args=args)
        self.listeners = listeners.Listeners(self, args=args)

        self.listenertemplatesv2 = ListenerTemplateService(self)
        self.listenersv2 = ListenerService(self)
        self.stagertemplatesv2 = StagerTemplateService(self)
        self.stagersv2 = StagerService(self)
        self.usersv2 = UserService(self)
        self.bypassesv2 = BypassService(self)
        self.obfuscationv2 = ObfuscationService(self)
        self.profilesv2 = ProfileService(self)
        self.credentialsv2 = CredentialService(self)
        self.hostsv2 = HostService(self)
        self.processesv2 = HostProcessService(self)
        self.modulesv2 = ModuleService(self)
        self.downloadsv2 = DownloadService(self)
        self.agenttasksv2 = AgentTaskService(self)
        self.agentfilesv2 = AgentFileService(self)
        self.agentsv2 = AgentService(self)
        self.pluginsv2 = PluginService(self)

        hooks_internal.initialize()

        self.resourceQueue = []
        # A hashtable of autruns based on agent language
        self.autoRuns = {}
        self.directory = {}

        self.get_directories()
        log.info("Empire starting up...")

    def plugin_socketio_message(self, plugin_name, msg):
        """
        Send socketio message to the socket address
        """
        log.info(f"{plugin_name}: {msg}")
        if self.socketio:
            try:  # https://stackoverflow.com/a/61331974/
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                loop.create_task(
                    self.socketio.emit(
                        f"plugins/{plugin_name}/notifications",
                        {"message": msg, "plugin_name": plugin_name},
                    )
                )
            else:
                asyncio.run(
                    self.socketio.emit(
                        f"plugins/{plugin_name}/notifications",
                        {"message": msg, "plugin_name": plugin_name},
                    )
                )

    def shutdown(self):
        """
        Perform any shutdown actions.
        """
        log.info("Empire shutting down...")

        # enumerate all active servers/listeners and shut them down
        self.listenersv2.shutdown_listeners()

        log.info("Shutting down plugins...")
        self.pluginsv2.shutdown()

    def get_directories(self):
        """
        Get download folder path from config file
        """
        directories = empire_config.yaml.get("directories", {})
        for key, value in directories.items():
            self.directory[key] = value
            if self.directory[key][-1] != "/":
                self.directory[key] += "/"
