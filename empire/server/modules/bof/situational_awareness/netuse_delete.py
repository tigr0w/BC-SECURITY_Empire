import base64

from empire.server.common.empire import MainMenu
from empire.server.core.exceptions import ModuleValidationException
from empire.server.core.module_models import EmpireModule
from empire.server.utils.bof_packer import process_arguments


def _flag(value) -> int:
    """Translate a True/False option (arrives as a bool, but tolerate strings)
    into the 1/0 short the netuse BOF reads."""
    return 1 if str(value).lower() in ("true", "1") else 0


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
        persist = _flag(params.get("Persist", False))
        force = _flag(params.get("Force", False))

        if not devicename:
            raise ModuleValidationException(
                "DeviceName is required (e.g. Z: or \\\\server\\share)."
            )

        # Custom generator required because the standard non-custom path cannot
        # inject the synthetic dispatch integer the netuse BOF reads first.  The
        # BOF calls WNetCancelConnection2W (wide), so strings are packed UTF-16LE (Z).
        # Persist/Force are exposed as True/False and translated to 1/0 shorts.
        # s=cmd(3=DELETE), Z=devicename(required), s=persist(1/0), s=force(1/0)
        hex_data = process_arguments(
            module.bof.format_string, ["3", devicename, persist, force]
        )

        return main_menu.modulesv2.format_bof_output(
            bof_data,
            hex_data,
            agent_language,
            obfuscate,
            module.bof.entry_point or "go",
        )
