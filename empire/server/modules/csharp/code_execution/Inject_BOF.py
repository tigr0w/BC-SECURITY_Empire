import base64
import json

import yaml

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
        b64_bof_data = params["File"].get_base64_file()

        compiler_dict: dict = yaml.safe_load(module.compiler_yaml)

        if params["Architecture"] == "x64":
            pass
        elif params["Architecture"] == "x86":
            compiler_dict[0]["ReferenceSourceLibraries"][0]["EmbeddedResources"][0][
                "Name"
            ] = "RunOF.beacon_funcs.x64.o"
            compiler_dict[0]["ReferenceSourceLibraries"][0]["EmbeddedResources"][0][
                "Location"
            ] = "RunOF.beacon_funcs.x64.o"
            compiler_dict[0]["ReferenceSourceLibraries"][0][
                "Location"
            ] = "RunOF\\RunOF32\\"

        compiler_yaml: str = yaml.dump(compiler_dict, sort_keys=False)

        script_file = main_menu.dotnet_compiler.compile_task(
            compiler_yaml,
            module.name,
            dotnet=params["DotNetVersion"].lower(),
            confuse=obfuscate,
        )

        params_dict = {}
        params_dict["File"] = f"-a:{b64_bof_data}" if params["File"] != "" else ""
        params_dict["Entrypoint"] = f"-e:{params['EntryPoint']}"
        params_dict["ArgumentList"] = f" {params['ArgumentList']}"

        param_json = json.dumps(params_dict)
        base64_json = base64.b64encode(param_json.encode("utf-8")).decode("utf-8")

        return f"{script_file}|,{base64_json}"
