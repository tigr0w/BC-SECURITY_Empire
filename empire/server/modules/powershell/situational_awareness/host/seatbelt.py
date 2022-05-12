from __future__ import print_function

import pathlib
from builtins import object, str
from typing import Dict

from empire.server.common import helpers
from empire.server.common.module_models import EmpireModule
from empire.server.utils import data_util
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

        script_end = 'Invoke-Seatbelt -Command "'

        # Add any arguments to the end execution of the script
        if params["Command"]:
            script_end += " " + str(params["Command"])
        if params["Group"]:
            script_end += " -group=" + str(params["Group"])
        if params["Computername"]:
            script_end += " -computername=" + str(params["Computername"])
        if params["Username"]:
            script_end += " -username=" + str(params["Username"])
        if params["Password"]:
            script_end += " -password=" + str(params["Password"])
        if params["Full"].lower() == "true":
            script_end += " -full"
        if params["Quiet"].lower() == "true":
            script_end += " -q"

        script_end = script_end.replace('" ', '"')
        script_end += '"'

        script = main_menu.modulesv2.finalize_module(
            script=script,
            script_end=script_end,
            obfuscate=obfuscate,
            obfuscation_command=obfuscation_command,
        )
        return script
