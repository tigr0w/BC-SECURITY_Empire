from __future__ import print_function

import pathlib
from builtins import object
from builtins import str
from typing import Dict

from empire.server.common import helpers
from empire.server.common.module_models import PydanticModule
from empire.server.utils import data_util
from empire.server.utils.module_util import handle_error_message


class Module(object):
    @staticmethod
    def generate(main_menu, module: PydanticModule, params: Dict, obfuscate: bool = False, obfuscation_command: str = ""):
        Passlist = params['Passlist']
        Verbose = params['Verbose']
        ServerType = params['ServerType']
        Loginacc = params['Loginacc']
        Loginpass = params['Loginpass']

        # read in the common module source code
        script, err = main_menu.modules.get_module_source(module_name=module.script_path, obfuscate=obfuscate, obfuscate_command=obfuscation_command)
        
        if err:
            return handle_error_message(err)

        script_end = " Fetch-Brute"
        if len(ServerType) >= 1:
            script_end += " -st "+ServerType
        script_end += " -pl "+Passlist
        if len(Verbose) >= 1:
            script_end += " -vbse "+Verbose
        if len(Loginacc) >= 1:
            script_end += " -lacc "+Loginacc
        if len(Loginpass) >= 1:
            script_end += " -lpass "+Loginpass

        script = main_menu.modules.finalize_module(script=script, script_end=script_end, obfuscate=obfuscate, obfuscation_command=obfuscation_command)
        return script
