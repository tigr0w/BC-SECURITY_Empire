from typing import Dict

from empire.server.core.db.base import SessionLocal
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
        script = ""

        with SessionLocal.begin() as db:
            for name in params["Bypasses"].split():
                bypass = main_menu.bypassesv2.get_by_name(db, name)
                if bypass:
                    script += bypass.code

        script = main_menu.modulesv2.finalize_module(
            script=script,
            script_end="",
            obfuscate=obfuscate or params["Obfuscate"],
            obfuscation_command=obfuscation_command
            if obfuscation_command != ""
            else params["ObfuscateCommand"],
        )
        return script
