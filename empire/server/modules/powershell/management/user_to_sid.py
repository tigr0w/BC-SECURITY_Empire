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
        script = '(New-Object System.Security.Principal.NTAccount("{}","{}")).Translate([System.Security.Principal.SecurityIdentifier]).Value'.format(
            params["Domain"], params["User"]
        )

        script = main_menu.modulesv2.finalize_module(
            script=script,
            script_end="",
            obfuscate=obfuscate,
            obfuscation_command=obfuscation_command,
        )
        return script
