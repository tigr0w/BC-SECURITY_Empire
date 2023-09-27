from typing import Dict

from empire.server.core.module_models import EmpireModule


class Module:
    @staticmethod
    def generate(
        main_menu,
        module: EmpireModule,
        params: Dict,
        obfuscate: bool = False,
        obfuscation_command: str = "",
    ):
        all_users = params["AllUsers"]

        if all_users.lower() == "true":
            script = "'Logging off all users.'; Start-Sleep -s 3; $null = (gwmi win32_operatingsystem).Win32Shutdown(4)"
        else:
            script = "'Logging off current user.'; Start-Sleep -s 3; shutdown /l /f"

        script = main_menu.modulesv2.finalize_module(
            script=script,
            script_end="",
            obfuscate=obfuscate,
            obfuscation_command=obfuscation_command,
        )
        return script
