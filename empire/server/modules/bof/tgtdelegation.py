import random

from empire.server.common.empire import MainMenu
from empire.server.core.module_models import EmpireModule


class Module:
    @staticmethod
    def generate(
        main_menu: MainMenu,
        module: EmpireModule,
        params: dict,
        obfuscate: bool = False,
        obfuscation_command: str = "",
    ):
        script_file, script_end = main_menu.modulesv2.generate_bof_data(
            module=module, params=params, obfuscate=obfuscate
        )

        nonce = random.randint(1000, 10000)
        script_end += f" -i:{nonce} -Z:{params['domain']} -Z:{params['SPN']}"
        return f"{script_file}|{script_end}"
