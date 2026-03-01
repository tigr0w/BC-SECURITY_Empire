import base64
import json

from empire.server.common.empire import MainMenu
from empire.server.core.module_models import EmpireModule
from empire.server.utils.bof_packer import Packer


class Module:
    @staticmethod
    def generate(
        main_menu: MainMenu,
        module: EmpireModule,
        params: dict,
        obfuscate: bool = False,
        obfuscation_command: str = "",
    ):
        bof_module = main_menu.modulesv2.modules["csharp_code_execution_runcoff"]
        script_file = main_menu.modulesv2.dotnet_compiler.compile_task(
            bof_module.compiler_yaml,
            bof_module.name,
            dot_net_version="net40",
            confuse=obfuscate,
        )

        script_path = main_menu.modulesv2.module_source_path / module.bof.x64
        bof_data = script_path.read_bytes()
        b64_bof_data = base64.b64encode(bof_data).decode("utf-8")

        packer = Packer()
        packer.addint(0)

        params_dict = {}
        params_dict["Entrypoint"] = "go"
        params_dict["File"] = b64_bof_data
        params_dict["HexData"] = packer.getbuffer_data()

        base64_json = base64.b64encode(json.dumps(params_dict).encode("utf-8")).decode(
            "utf-8"
        )

        return f"{script_file}|,{base64_json}"
