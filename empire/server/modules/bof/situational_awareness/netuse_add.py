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

        sharepath = params.get("SharePath", "")
        username = params.get("Username", "")
        password = params.get("Password", "")
        devicename = params.get("DeviceName", "")
        persist = _flag(params.get("Persist", False))
        requireprivacy = _flag(params.get("RequirePrivacy", False))

        if not sharepath:
            raise ModuleValidationException(
                "SharePath is required (e.g. \\\\server\\share)."
            )

        # Custom generator required because the standard non-custom path builds
        # arg_list from params dict values only and cannot inject the synthetic
        # dispatch integer that the netuse BOF reads first.  The BOF calls the
        # wide WNet APIs (WNetAddConnection2W), so strings are packed as UTF-16LE
        # (format Z), not ANSI (z).  Persist/RequirePrivacy are exposed as
        # True/False and translated to the 1/0 shorts the BOF reads.
        # s=cmd(1=ADD), Z=sharepath(required), Z=username(empty→current creds),
        # Z=password(empty→current creds), Z=devicename(empty→no drive letter),
        # s=persist(1/0), s=requirePrivacy(1/0)
        hex_data = process_arguments(
            module.bof.format_string,
            ["1", sharepath, username, password, devicename, persist, requireprivacy],
        )

        return main_menu.modulesv2.format_bof_output(
            bof_data,
            hex_data,
            agent_language,
            obfuscate,
            module.bof.entry_point or "go",
        )
