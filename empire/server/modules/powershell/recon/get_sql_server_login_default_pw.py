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
        username = params["Username"]
        password = params["Password"]
        instance = params["Instance"]
        check_all = params["CheckAll"]

        if check_all:
            # read in the common module source code
            script, err = main_menu.modulesv2.get_module_source(
                module_name="recon/Get-SQLInstanceDomain.ps1",
                obfuscate=obfuscate,
                obfuscate_command=obfuscation_command,
            )

            script_end = " Get-SQLInstanceDomain "
            if username != "":
                script_end += " -Username " + username
            if password != "":
                script_end += " -Password " + password
            script_end += " | Select Instance | "
        script_end += " Get-SQLServerLoginDefaultPw"

        if instance != "" and not check_all:
            # read in the common module source code
            script, err = main_menu.modulesv2.get_module_source(
                module_name="recon/Get-SQLServerLoginDefaultPw.ps1",
                obfuscate=obfuscate,
                obfuscate_command=obfuscation_command,
            )
            script_end += " -Instance " + instance

        script = main_menu.modulesv2.finalize_module(
            script=script,
            script_end=script_end,
            obfuscate=obfuscate,
            obfuscation_command=obfuscation_command,
        )
        return script
