from __future__ import print_function

import base64
from builtins import object, str
from pathlib import Path
from typing import Dict

import yaml

from empire.server.core.config import empire_config
from empire.server.core.db import models
from empire.server.core.db.base import SessionLocal
from empire.server.core.module_models import EmpireModule


class Module(object):
    @staticmethod
    def generate(
        main_menu,
        module: EmpireModule,
        params: Dict,
        obfuscate: bool = False,
        obfuscation_command: str = "",
    ):
        if params["File"] != "":
            with SessionLocal() as db:
                location = (
                    db.query(models.Download.location)
                    .filter(models.Download.filename == params["File"])
                    .scalar()
                )

            location_path = Path(location)
            with location_path.open("rb") as data:
                bof_data = data.read()
            b64_bof_data = base64.b64encode(bof_data).decode("utf-8")

        compiler = main_menu.pluginsv2.get_by_id("csharpserver")
        if not compiler.status == "ON":
            return None, "csharpserver plugin not running"

        # Convert compiler.yaml to python dict
        compiler_dict: Dict = yaml.safe_load(module.compiler_yaml)
        # delete the 'Empire' key
        del compiler_dict[0]["Empire"]
        # convert back to yaml string

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
        if params["File"] != "":
            script_end = f",-a:{b64_bof_data}"
        else:
            script_end = f","

        if params["EntryPoint"] != "":
            script_end += f" -e:{params['EntryPoint']}"
        if params["ArgumentList"] != "":
            script_end += f" {params['ArgumentList']}"
        return f"{script_file}|{script_end}", None
