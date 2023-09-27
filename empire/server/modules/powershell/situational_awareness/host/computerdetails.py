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

        script_end = ""
        outputf = params.get("OutputFunction", "Out-String")

        for option, values in params.items():
            if option.lower() != "agent" and option.lower() != "outputfunction":
                if values and values != "":
                    if option == "4624":
                        script_end += "$SecurityLog = Get-EventLog -LogName Security; $Filtered4624 = Find-4624Logons $SecurityLog;"
                        script_end += 'Write-Output "Event ID 4624 (Logon):`n";'
                        script_end += "Write-Output $Filtered4624.Values"
                        script_end += f" | {outputf}"
                        script = main_menu.modulesv2.finalize_module(
                            script=script,
                            script_end=script_end,
                            obfuscate=obfuscate,
                            obfuscation_command=obfuscation_command,
                        )
                        return script

                    if option == "4648":
                        script_end += "$SecurityLog = Get-EventLog -LogName Security; $Filtered4648 = Find-4648Logons $SecurityLog;"
                        script_end += 'Write-Output "Event ID 4648 (Explicit Credential Logon):`n";'
                        script_end += "Write-Output $Filtered4648.Values"
                        script_end += f" | {outputf}"
                        script = main_menu.modulesv2.finalize_module(
                            script=script,
                            script_end=script_end,
                            obfuscate=obfuscate,
                            obfuscation_command=obfuscation_command,
                        )
                        return script

                    if option == "AppLocker":
                        script_end += "$AppLockerLogs = Find-AppLockerLogs;"
                        script_end += 'Write-Output "AppLocker Process Starts:`n";'
                        script_end += "Write-Output $AppLockerLogs.Values"
                        script_end += f" | {outputf}"
                        script = main_menu.modulesv2.finalize_module(
                            script=script,
                            script_end=script_end,
                            obfuscate=obfuscate,
                            obfuscation_command=obfuscation_command,
                        )
                        return script

                    if option == "PSLogs":
                        script_end += "$PSLogs = Find-PSScriptsInPSAppLog;"
                        script_end += 'Write-Output "PowerShell Script Executions:`n";'
                        script_end += "Write-Output $PSLogs.Values"
                        script_end += f" | {outputf}"
                        script = main_menu.modulesv2.finalize_module(
                            script=script,
                            script_end=script_end,
                            obfuscate=obfuscate,
                            obfuscation_command=obfuscation_command,
                        )
                        return script

                    if option == "SavedRDP":
                        script_end += "$RdpClientData = Find-RDPClientConnections;"
                        script_end += 'Write-Output "RDP Client Data:`n";'
                        script_end += "Write-Output $RdpClientData.Values"
                        script_end += f" | {outputf}"
                        script = main_menu.modulesv2.finalize_module(
                            script=script,
                            script_end=script_end,
                            obfuscate=obfuscate,
                            obfuscation_command=obfuscation_command,
                        )
                        return script

        # if we get to this point, no switched were specified
        script_end += "Get-ComputerDetails -Limit " + str(params["Limit"])
        if outputf == "Out-String":
            script_end += (
                " -ToString | "
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

        script = main_menu.modulesv2.finalize_module(
            script=script,
            script_end=script_end,
            obfuscate=obfuscate,
            obfuscation_command=obfuscation_command,
        )
        return script
