from __future__ import print_function

import base64
import pathlib
from builtins import object, str
from typing import Dict

from empire.server.common import helpers
from empire.server.common.module_models import PydanticModule
from empire.server.utils import data_util
from empire.server.utils.module_util import handle_error_message


class Module(object):
    @staticmethod
    def generate(
        main_menu,
        module: PydanticModule,
        params: Dict,
        obfuscate: bool = False,
        obfuscation_command: str = "",
    ):

        # read in the common module source code
        script, err = main_menu.modules.get_module_source(
            module_name=module.script_path,
            obfuscate=obfuscate,
            obfuscate_command=obfuscation_command,
        )

        if err:
            return handle_error_message(err)

        with open(f"{main_menu.directory['downloads']}{params['File']}", "rb") as data:
            bof_data = data.read()
        bof_data = base64.b64encode(bof_data).decode("utf-8")

        script_end = f"$bofbytes = [System.Convert]::FromBase64String('{ bof_data }');"
        script_end += (
            f"\nInvoke-Bof -BOFBytes $bofbytes -EntryPoint { params['EntryPoint'] }"
        )

        if params["ArguementList"] != "":
            script_end += f" -ArgumentList { params['ArguementList'] }"

        script = main_menu.modules.finalize_module(
            script=script,
            script_end=script_end,
            obfuscate=obfuscate,
            obfuscation_command=obfuscation_command,
        )
        return script
