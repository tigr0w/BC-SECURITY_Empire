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
        resource = f"\\\\{params['System']}\\{params['Namespace']}"

        # Build the params dictionary with required prefixes
        params_dict = {
            "Architecture": params["Architecture"],
            "System": f"-Z:{params['System']}",
            "Namespace": f"-Z:{params['Namespace']}",
            "Query": f"-Z:{params['Query']}",
            "Resource": f"-Z:{resource}",
        }

        return main_menu.modulesv2.generate_script_bof(
            module=module, params=params_dict, obfuscate=obfuscate
        )
