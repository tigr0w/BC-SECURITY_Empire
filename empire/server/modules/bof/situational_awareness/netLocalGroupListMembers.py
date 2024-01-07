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

        script_end += f" -s:1 -Z:{params['Server']} -Z:{params['Group']}"
        return f"{script_file}|{script_end}"
