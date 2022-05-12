from __future__ import print_function

import pathlib
from builtins import object, str
from typing import Dict

from empire.server.common import helpers
from empire.server.common.module_models import EmpireModule
from empire.server.utils import data_util


class Module(object):
    @staticmethod
    def generate(
        main_menu,
        module: EmpireModule,
        params: Dict,
        obfuscate: bool = False,
        obfuscation_command: str = "",
    ):

        script = (
            '(New-Object System.Security.Principal.NTAccount("%s","%s")).Translate([System.Security.Principal.SecurityIdentifier]).Value'
            % (params["Domain"], params["User"])
        )

        script = main_menu.modulesv2.finalize_module(
            script=script,
            script_end="",
            obfuscate=obfuscate,
            obfuscation_command=obfuscation_command,
        )
        return script
