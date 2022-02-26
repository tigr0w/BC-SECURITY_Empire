from __future__ import print_function

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

        script_path = params["ScriptPath"]
        script_cmd = params["ScriptCmd"]
        script = ""

        if script_path != "":
            try:
                with open(f"{script_path}", "r") as data:
                    script = data.read()
            except:
                return handle_error_message(
                    "[!] Could not read script source path at: " + str(script_path)
                )

            script += "\n"

        script += "%s" % script_cmd

        script = main_menu.modulesv2.finalize_module(
            script=script,
            script_end="",
            obfuscate=obfuscate,
            obfuscation_command=obfuscation_command,
        )
        return script
