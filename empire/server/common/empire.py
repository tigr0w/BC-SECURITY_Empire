"""

The main controller class for Empire.

This is what's launched from ./empire.
Contains the Main, Listener, Agents, Agent, and Module
menu loops.

"""
from __future__ import absolute_import

import asyncio
import logging
import os
import threading
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
from empire.server.v2.core.keyword_service import KeywordService
from empire.server.v2.core.listener_service import ListenerService
from empire.server.v2.core.listener_template_service import ListenerTemplateService
from empire.server.v2.core.module_service import ModuleService
from empire.server.v2.core.plugin_service import PluginService
from empire.server.v2.core.profile_service import ProfileService
from empire.server.v2.core.stager_service import StagerService
from empire.server.v2.core.stager_template_service import StagerTemplateService
from empire.server.v2.core.user_service import UserService

from . import agents, credentials, helpers, listeners, stagers

VERSION = "5.0.0-alpha1 BC Security Fork"

log = logging.getLogger(__name__)


class MainMenu(object):
    """
    The main class used by Empire to drive the 'main' menu
    displayed when Empire starts.
    """

    def __init__(self, args=None):
        time.sleep(1)

        self.lock = threading.Lock()

        # pull out some common configuration information
        (
            self.isroot,
            self.installPath,
            self.ipWhiteList,
            self.ipBlackList,
            self.obfuscate,
            self.obfuscateCommand,
        ) = data_util.get_config(
            "rootuser, install_path,ip_whitelist,ip_blacklist,obfuscate,obfuscate_command"
        )

        # parse/handle any passed command line arguments
        self.args = args

        self.socketio: Optional[SocketIO] = None

        self.agents = agents.Agents(self, args=args)

        self.listenertemplatesv2 = ListenerTemplateService(self)
        self.listenersv2 = ListenerService(self)
        self.stagertemplatesv2 = StagerTemplateService(self)
        self.stagersv2 = StagerService(self)
        self.usersv2 = UserService(self)
        self.bypassesv2 = BypassService(self)
        self.keywordsv2 = KeywordService(self)
        self.profilesv2 = ProfileService(self)
        self.credentialsv2 = CredentialService(self)
        self.hostsv2 = HostService(self)
        self.processesv2 = HostProcessService(self)
        self.modulesv2 = ModuleService(self)
        self.downloadsv2 = DownloadService(self)

        # instantiate the agents, listeners, and stagers objects
        self.credentials = credentials.Credentials(self, args=args)
        self.stagers = stagers.Stagers(self, args=args)
        self.listeners = listeners.Listeners(self, args=args)

        # todo lol i hate this. moving below the other instantiations.
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
        # todo vr plugins could get their own loggers in the future.
        log.info(f"{plugin_name}: {msg}")
        if self.socketio:
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

    def preobfuscate_modules(self, obfuscation_command, reobfuscate=False):
        """
        Preobfuscate PowerShell module_source files
        """
        if not data_util.is_powershell_installed():
            log.error(
                "PowerShell is not installed and is required to use obfuscation, please install it first."
            )
            return

        # Preobfuscate all module_source files
        files = [file for file in helpers.get_module_source_files()]

        for file in files:
            file = os.getcwd() + "/" + file
            if reobfuscate or not data_util.is_obfuscated(file):
                message = f"Obfuscating {os.path.basename(file)}..."
                log.info(message)
            else:
                log.warning(
                    f"{os.path.basename(file)} was already obfuscated. Not reobfuscating."
                )
            data_util.obfuscate_module(file, obfuscation_command, reobfuscate)

    def get_directories(self):
        """
        Get download folder path from config file
        """
        directories = empire_config.yaml.get("directories", {})
        for key, value in directories.items():
            self.directory[key] = value
            if self.directory[key][-1] != "/":
                self.directory[key] += "/"
