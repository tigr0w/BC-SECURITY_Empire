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
        del compiler_dict[0]["Empire"]

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

        script_end = f",-a:{b64_bof_data}" if params["File"] != "" else ","

        if params["EntryPoint"] != "":
            script_end += f" -e:{params['EntryPoint']}"
        if params["ArgumentList"] != "":
            script_end += f" {params['ArgumentList']}"
        return f"{script_file}|{script_end}", None
