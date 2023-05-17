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
        # read in the common module source code
        script, err = main_menu.modulesv2.get_module_source(
            module_name=module.script_path,
            obfuscate=obfuscate,
            obfuscate_command=obfuscation_command,
        )

        if err:
            return handle_error_message(err)

        bof_data = params["File"].get_base64_file()

        script_end = f"$bofbytes = [System.Convert]::FromBase64String('{ bof_data }');"
        script_end += (
            f"\nInvoke-Bof -BOFBytes $bofbytes -EntryPoint { params['EntryPoint'] }"
        )

        if params["ArgumentList"] != "":
            script_end += f" -ArgumentList { params['ArgumentList'] }"

        script = main_menu.modulesv2.finalize_module(
            script=script,
            script_end=script_end,
            obfuscate=obfuscate,
            obfuscation_command=obfuscation_command,
        )
        return script
