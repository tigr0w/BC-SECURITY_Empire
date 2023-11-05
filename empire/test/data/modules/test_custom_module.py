from empire.server.core.module_models import EmpireModule


class Module:
    @staticmethod
    def generate(
        main_menu,
        module: EmpireModule,
        params: dict,
        obfuscate: bool = False,
        obfuscation_command: str = "",
    ):
        return "This is the module code."
