import base64

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

        devicename = params.get("DeviceName", "")

        # Custom generator required because the standard non-custom path cannot
        # inject the synthetic dispatch integer the netuse BOF reads first.  The
        # BOF calls WNetEnumResourceW (wide), so strings are packed UTF-16LE (Z).
        # s=cmd(2=LIST), Z=devicename (empty → BOF lists all connections)
        hex_data = process_arguments(module.bof.format_string, ["2", devicename])

        return main_menu.modulesv2.format_bof_output(
            bof_data,
            hex_data,
            agent_language,
            obfuscate,
            module.bof.entry_point or "go",
        )
