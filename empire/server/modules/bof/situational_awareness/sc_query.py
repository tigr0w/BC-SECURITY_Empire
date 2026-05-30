import base64
import shlex

from empire.server.common.empire import MainMenu
from empire.server.core.module_models import EmpireModule
from empire.server.utils.bof_packer import process_arguments


class Module:
    @staticmethod
    def generate(
        main_menu: MainMenu,
        module: EmpireModule,
        params: dict,
        obfuscate: bool = False,
        obfuscation_command: str = "",
        agent_language: str = "go",
        **kwargs,
    ):
        arch = params.get("Architecture", "x64")
        script_path = main_menu.modulesv2.module_source_path / (
            module.bof.x86 if arch == "x86" else module.bof.x64
        )
        bof_data = base64.b64encode(script_path.read_bytes()).decode()

        hostname = params.get("Hostname", "")
        servicename = params.get("ServiceName", "")

        # Pass quoted-empty strings directly to process_arguments so shlex.split
        # preserves slen=1 (null-terminator only). module_service's empty→" "
        # substitution would produce slen=2, breaking the BOF's slen==1 branch
        # (enumerate all services) and OpenSCManagerA local-machine resolution.
        hn = shlex.quote(hostname) if hostname else '""'
        sn = shlex.quote(servicename) if servicename else '""'

        hex_data = process_arguments(module.bof.format_string, f"{hn} {sn}")

        return main_menu.modulesv2.format_bof_output(
            bof_data,
            hex_data,
            agent_language,
            obfuscate,
            module.bof.entry_point or "go",
        )
