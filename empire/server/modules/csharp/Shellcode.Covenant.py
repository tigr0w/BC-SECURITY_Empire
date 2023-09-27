from typing import Dict

import yaml

from empire.server.core.module_models import EmpireModule


class Module:
    @staticmethod
    def generate(
        main_menu,
        module: EmpireModule,
        params: Dict,
        obfuscate: bool = False,
        obfuscation_command: str = "",
    ):
        try:
            base64_shellcode = params["File"].get_base64_file()
        except Exception as e:
            return None, f"Failed to get base64 encoded shellcode: {e}"

        compiler = main_menu.pluginsv2.get_by_id("csharpserver")
        if not compiler.status == "ON":
            return None, "csharpserver plugin not running"

        # Convert compiler.yaml to python dict
        compiler_dict: Dict = yaml.safe_load(module.compiler_yaml)
        # delete the 'Empire' key
        del compiler_dict[0]["Empire"]
        # convert back to yaml string
        compiler_yaml: str = yaml.dump(compiler_dict, sort_keys=False)

        file_name = compiler.do_send_message(
            compiler_yaml, module.name, confuse=obfuscate
        )
        if file_name == "failed":
            return None, "module compile failed"

        script_file = (
            main_menu.installPath
            + "/csharp/Covenant/Data/Tasks/CSharp/Compiled/"
            + (params["DotNetVersion"]).lower()
            + "/"
            + file_name
            + ".compiled"
        )

        script_end = f",{base64_shellcode} "
        return f"{script_file}|{script_end}", None
