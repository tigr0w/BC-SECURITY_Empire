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
        base64_assembly = params["File"].get_base64_file()

        compiler_dict: dict = yaml.safe_load(module.compiler_yaml)
        del compiler_dict[0]["Empire"]
        compiler_yaml: str = yaml.dump(compiler_dict, sort_keys=False)

        script_file = main_menu.dotnet_compiler.compile_task(
            compiler_yaml,
            module.name,
            dotnet=params["DotNetVersion"].lower(),
            confuse=obfuscate,
        )

        script_end = f",{base64_assembly}, {params['Parameters']}"
        return f"{script_file}|{script_end}", None
