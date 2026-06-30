from empire.server.common.empire import MainMenu
from empire.server.core.module_models import EmpireModule
from empire.server.core.module_service import auto_finalize, auto_get_source
from empire.server.utils.option_util import coerce_legacy_value


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
        script_end = "\nFind-Fruit"

        show_all = params["ShowAll"]

        for option, raw_value in params.items():
            values = coerce_legacy_value(raw_value)
            if (
                (
                    option.lower() != "agent"
                    and option.lower() != "showall"
                    and option.lower() != "outputfunction"
                )
                and values
                and values != ""
            ):
                if isinstance(raw_value, bool):
                    # Native boolean -> [switch]: bare flag only when set,
                    # never "-Option False".
                    if raw_value:
                        script_end += " -" + str(option)
                else:
                    script_end += " -" + str(option) + " " + str(values)

        if not show_all:
            script_end += " | ?{$_.Status -eq 'OK'}"

        script_end += " | Format-Table -AutoSize"
        outputf = params.get("OutputFunction", "Out-String")
        script_end += (
            f" | {outputf} | "
            + '%{$_ + "`n"};"`n'
            + str(module.name.split("/")[-1])
            + ' completed!"'
        )

        return script, script_end
