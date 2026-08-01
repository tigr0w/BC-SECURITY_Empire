import base64

from empire.server.common.empire import MainMenu
from empire.server.core.module_models import EmpireModule
from empire.server.utils.bof_packer import process_arguments


def _flag(value) -> int:
    """Translate a True/False option (arrives as a bool, but tolerate strings)
    into the 1/0 int the netuserenum BOF reads."""
    return 1 if str(value).lower() in ("true", "1") else 0


# UserFilter labels map to the numeric account filter the netuserenum BOF reads.
_USER_FILTER = {
    "All users": 1,
    "Locked out": 2,
    "Disabled": 3,
    "Active accounts only": 4,
}


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

        # UseDomain is exposed as True/False and UserFilter as descriptive labels;
        # both are translated to the integers the BOF reads (1=domain/0=local,
        # and the 1-4 account filter).  i=useDomain(1/0), i=userFilter(1-4)
        use_domain = _flag(params.get("UseDomain", False))
        user_filter = _USER_FILTER.get(params.get("UserFilter", "All users"), 1)

        hex_data = process_arguments(
            module.bof.format_string, [use_domain, user_filter]
        )

        return main_menu.modulesv2.format_bof_output(
            bof_data,
            hex_data,
            agent_language,
            obfuscate,
            module.bof.entry_point or "go",
        )
