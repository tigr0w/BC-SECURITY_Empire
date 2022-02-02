"""

The main controller class for Empire.

This is what's launched from ./empire.
Contains the Main, Listener, Agents, Agent, and Module
menu loops.

"""
from __future__ import absolute_import
from __future__ import print_function

from builtins import input
from builtins import str
from typing import Optional
from pydispatch import dispatcher

import threading
import json
import time

# Empire imports
from empire.server.common import hooks_internal
from empire.server.utils import data_util

from empire.server.v2.core.agent_service import AgentService
from empire.server.v2.core.agent_task_service import AgentTaskService
from empire.server.v2.core.agent_file_service import AgentFileService
from empire.server.v2.core.bypass_service import BypassService
from empire.server.v2.core.credential_service import CredentialService
from empire.server.v2.core.host_service import HostService
from empire.server.v2.core.host_process_service import HostProcessService
from empire.server.v2.core.keyword_service import KeywordService
from empire.server.v2.core.listener_service import ListenerService
from empire.server.v2.core.listener_template_service import ListenerTemplateService
from empire.server.v2.core.profile_service import ProfileService
from empire.server.v2.core.stager_service import StagerService
from empire.server.v2.core.stager_template_service import StagerTemplateService
from empire.server.v2.core.user_service import UserService
from empire.server.v2.core.module_service import ModuleService
from empire.server.v2.core.download_service import DownloadService
from empire.server.v2.core.plugin_service import PluginService

from . import helpers
from . import agents
from . import listeners
from . import stagers
from . import credentials
from .events import log_event
from prompt_toolkit import PromptSession, HTML
from prompt_toolkit.patch_stdout import patch_stdout
from empire.server.database.base import SessionLocal
from empire.server.database import models
from sqlalchemy import or_, func, and_

VERSION = "5.0.0-alpha1 BC Security Fork"


class MainMenu(object):
    """
    The main class used by Empire to drive the 'main' menu
    displayed when Empire starts.
    """

    def __init__(self, args=None):

        # set up the event handling system
        # dispatcher.connect(self.handle_event, sender=dispatcher.Any)

        time.sleep(1)

        self.lock = threading.Lock()

        # pull out some common configuration information
        (self.isroot, self.installPath, self.ipWhiteList, self.ipBlackList, self.obfuscate,
         self.obfuscateCommand) = data_util.get_config(
            'rootuser, install_path,ip_whitelist,ip_blacklist,obfuscate,obfuscate_command')

        # change the default prompt for the user
        self.prompt = '(Empire) > '

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

        message = "[*] Empire starting up..."
        signal = json.dumps({
            'print': True,
            'message': message
        })
        # dispatcher.send(signal, sender="empire")

    def handle_event(self, signal, sender):
        """
        Whenver an event is received from the dispatcher, log it to the DB,
        decide whether it should be printed, and if so, print it.
        If self.args.debug, also log all events to a file.
        """
        # load up the signal so we can inspect it
        try:
            signal_data = json.loads(signal)
        except ValueError:
            print(helpers.color("[!] Error: bad signal received {} from sender {}".format(signal, sender)))
            return

        # if this is related to a task, set task_id; this is its own column in
        # the DB (else the column will be set to None/null)
        task_id = None
        if 'task_id' in signal_data:
            task_id = signal_data['task_id']

        if 'event_type' in signal_data:
            event_type = signal_data['event_type']
        else:
            event_type = 'dispatched_event'

        # print any signal that indicates we should
        if ('print' in signal_data and signal_data['print']):
            print(helpers.color(signal_data['message']))

        # get a db cursor, log this event to the DB, then close the cursor
        # TODO instead of "dispatched_event" put something useful in the "event_type" column
        log_event(sender, event_type, json.dumps(signal_data), task_id=task_id)

        # if --debug X is passed, log out all dispatcher signals
        if self.args.debug:
            with open('empire.debug', 'a') as debug_file:
                debug_file.write("%s %s : %s\n" % (helpers.get_datetime(), sender, signal))

            if self.args.debug == '2':
                # if --debug 2, also print the output to the screen
                print(" %s : %s" % (sender, signal))

    def plugin_socketio_message(self, plugin_name, msg):
        """
        Send socketio message to the socket address
        """
        if self.args.debug is not None:
            print(helpers.color(msg))
        if self.socketio:
            self.socketio.emit(f'plugins/{plugin_name}/notifications', {'message': msg, 'plugin_name': plugin_name})

    def shutdown(self):
        """
        Perform any shutdown actions.
        """
        print("\n" + helpers.color("[!] Shutting down..."))

        message = "[*] Empire shutting down..."
        signal = json.dumps({
            'print': True,
            'message': message
        })
        # dispatcher.send(signal, sender="empire")

        # enumerate all active servers/listeners and shut them down
        self.listenersv2.shutdown_listeners()

        message = "[*] Shutting down plugins..."
        signal = json.dumps({
            'print': True,
            'message': message
        })
        # dispatcher.send(signal, sender="empire")
        self.pluginsv2.shutdown()

    def teamserver(self):
        """
        The main cmdloop logic that handles navigation to other menus.
        """
        session = PromptSession(
            complete_in_thread=True,
            bottom_toolbar=self.bottom_toolbar,
            refresh_interval=5
        )

        while True:
            try:
                with patch_stdout(raw=True):
                    text = session.prompt('Server > ', refresh_interval=None)
                    print(helpers.color('[!] Type exit to quit'))
            except KeyboardInterrupt:
                print(helpers.color("[!] Type exit to quit"))
                continue  # Control-C pressed. Try again.
            except EOFError:
                break  # Control-D pressed.

            if text == 'exit':
                choice = input(helpers.color("[>] Exit? [y/N] ", "red"))
                if choice.lower() == "y":
                    self.shutdown()
                    return True
                else:
                    pass

    def bottom_toolbar(self):
        return HTML(f'EMPIRE TEAM SERVER | ' +
                    str(len(self.agents.agents)) + ' Agent(s) | ' +
                    str(len(self.listenersv2.get_active_listeners())) + ' Listener(s) | ' +
                    str(len(self.pluginsv2.get_all())) + ' Plugin(s)')

    def substring(self, session, column, delimeter):
        """
        https://stackoverflow.com/a/57763081
        """
        if session.bind.dialect.name == 'sqlite':
            return func.substr(column, func.instr(column, delimeter) + 1)
        elif session.bind.dialect.name == 'mysql':
            return func.substring_index(column, delimeter, -1)

    # TODO VR: I don't think this is really necessary anymore.
    # Ive already turned off the reporting table.
    # Since it is only pulling tasks and checkins, it can just use the
    # /tasks endpoint. We can still write to a master.log but should utilize python logging for that.
    # I suppose we could have some /reporting endpoints to export certain data to csvs or something,
    # but that seems like overkill since the session and credential logs are just csv dumps of the db basically.
    def run_report_query(self):
        with SessionLocal.begin() as db:
            reporting_sub_query = db \
                .query(models.Reporting, self.substring(db, models.Reporting.name, '/').label('agent_name')) \
                .filter(and_(models.Reporting.name.ilike('agent%'),
                             or_(models.Reporting.event_type == 'task',
                                 models.Reporting.event_type == 'checkin'))) \
                .subquery()

            return db \
                .query(reporting_sub_query.c.timestamp,
                       reporting_sub_query.c.event_type,
                       reporting_sub_query.c.agent_name,
                       reporting_sub_query.c.taskID,
                       models.Agent.hostname,
                       models.User.username,
                       models.Tasking.input.label('task'),
                       models.Tasking.output.label('results')) \
                .join(models.Tasking, and_(models.Tasking.id == reporting_sub_query.c.taskID,
                                           models.Tasking.agent_id == reporting_sub_query.c.agent_name), isouter=True) \
                .join(models.User, models.User.id == models.Tasking.user_id, isouter=True) \
                .join(models.Agent, models.Agent.session_id == reporting_sub_query.c.agent_name, isouter=True) \
                .all()

    def generate_report(self):
        """
        Produce report CSV and log files: sessions.csv, credentials.csv, master.log
        """
        rows = SessionLocal().query(models.Agent.session_id, models.Agent.hostname, models.Agent.username,
                                    models.Agent.checkin_time).all()

        print(helpers.color(f"[*] Writing {self.installPath}/data/sessions.csv"))
        try:
            self.lock.acquire()
            with open(self.installPath + '/data/sessions.csv', 'w') as f:
                f.write("SessionID, Hostname, User Name, First Check-in\n")
                for row in rows:
                    f.write(row[0] + ',' + row[1] + ',' + row[2] + ',' + str(row[3]) + '\n')
        finally:
            self.lock.release()

        # Credentials CSV
        rows = SessionLocal().query(models.Credential.domain,
                                    models.Credential.username,
                                    models.Credential.host,
                                    models.Credential.credtype,
                                    models.Credential.password) \
            .order_by(models.Credential.domain, models.Credential.credtype, models.Credential.host) \
            .all()

        print(helpers.color(f"[*] Writing {self.installPath}/data/credentials.csv"))
        try:
            self.lock.acquire()
            with open(self.installPath + '/data/credentials.csv', 'w') as f:
                f.write('Domain, Username, Host, Cred Type, Password\n')
                for row in rows:
                    # todo vr maybe can replace with
                    #  f.write(f'{row.domain},{row.username},{row.host},{row.credtype},{row.password}\n')
                    row = list(row)
                    for n in range(len(row)):
                        if isinstance(row[n], bytes):
                            row[n] = row[n].decode('UTF-8')
                    f.write(row[0] + ',' + row[1] + ',' + row[2] + ',' + row[3] + ',' + row[4] + '\n')
        finally:
            self.lock.release()

        # Empire Log
        rows = self.run_report_query()

        print(helpers.color(f"[*] Writing {self.installPath}/data/master.log"))
        try:
            self.lock.acquire()
            with open(self.installPath + '/data/master.log', 'w') as f:
                f.write('Empire Master Taskings & Results Log by timestamp\n')
                f.write('=' * 50 + '\n\n')
                for row in rows:
                    # todo vr maybe can replace with
                    #  f.write(f'\n{xstr(row.timestamp)} - {xstr(row.username)} ({xstr(row.username)})> {xstr(row.hostname)}\n{xstr(row.taskID)}\n{xstr(row.results)}\n')
                    row = list(row)
                    for n in range(len(row)):
                        if isinstance(row[n], bytes):
                            row[n] = row[n].decode('UTF-8')
                    f.write('\n' + xstr(row[0]) + ' - ' + xstr(row[3]) + ' (' + xstr(row[2]) + ')> ' + xstr(
                        row[5]) + '\n' + xstr(row[6]) + '\n' + xstr(row[7]) + '\n')
        finally:
            self.lock.release()

        return f'{self.installPath}/data'

    def preobfuscate_modules(self, obfuscation_command, reobfuscate=False):
        """
        Preobfuscate PowerShell module_source files
        """
        if not data_util.is_powershell_installed():
            print(helpers.color(
                "[!] PowerShell is not installed and is required to use obfuscation, please install it first."))
            return

        # Preobfuscate all module_source files
        files = [file for file in helpers.get_module_source_files()]

        for file in files:
            file = os.getcwd() + '/' + file
            if reobfuscate or not data_util.is_obfuscated(file):
                message = "[*] Obfuscating {}...".format(os.path.basename(file))
                signal = json.dumps({
                    'print': True,
                    'message': message,
                    'obfuscated_file': os.path.basename(file)
                })
                dispatcher.send(signal, sender="empire")
            else:
                print(helpers.color("[*] " + os.path.basename(file) + " was already obfuscated. Not reobfuscating."))
            data_util.obfuscate_module(file, obfuscation_command, reobfuscate)


def xstr(s):
    """
    Safely cast to a string with a handler for None
    """
    if s is None:
        return ''
    return str(s)
