import base64

from empire.server.common.empire import MainMenu
from empire.server.core.module_models import EmpireModule
from empire.server.utils.bof_packer import process_arguments

# RecordType labels map to the numeric DNS record type the nslookup BOF reads.
_RECORD_TYPE = {
    "A": 1,
    "NS": 2,
    "CNAME": 5,
    "MX": 15,
    "TXT": 16,
    "AAAA": 28,
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

        target = params.get("Target", "")
        server = params.get("Server", "")
        # RecordType is exposed as a label (A, AAAA, ...) and translated to the
        # numeric DNS type the BOF reads.  An empty Server packs as slen=1, which
        # the BOF treats as "use the system default DNS server".
        # z=target, z=server(empty→default), s=recordType
        record_type = _RECORD_TYPE.get(params.get("RecordType", "A"), 1)

        hex_data = process_arguments(
            module.bof.format_string, [target, server, record_type]
        )

        return main_menu.modulesv2.format_bof_output(
            bof_data,
            hex_data,
            agent_language,
            obfuscate,
            module.bof.entry_point or "go",
        )
