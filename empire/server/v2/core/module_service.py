import fnmatch
import importlib.util
import logging
import os
import pathlib
from typing import Dict, List, Optional, Tuple

import yaml
from sqlalchemy.orm import Session

from empire.server.common import helpers
from empire.server.common.config import empire_config
from empire.server.common.converter.load_covenant import _convert_covenant_to_empire
from empire.server.common.module_models import LanguageEnum, PydanticModule
from empire.server.database import models
from empire.server.database.base import SessionLocal
from empire.server.utils import data_util
from empire.server.utils.type_util import safe_cast
from empire.server.v2.api.module.module_dto import (
    ModuleBulkUpdateRequest,
    ModuleUpdateRequest,
)

log = logging.getLogger(__name__)


class ModuleService(object):
    def __init__(self, main_menu):
        self.main_menu = main_menu
        self.modules = {}

        with SessionLocal.begin() as db:
            self._load_modules(db)

    def get_all(self):
        return self.modules

    def get_by_id(self, uid: str):
        return self.modules.get(uid)

    def update_module(
        self, db: Session, module: PydanticModule, module_req: ModuleUpdateRequest
    ):
        db_module: models.Module = (
            db.query(models.Module).filter(models.Module.id == module.id).first()
        )
        db_module.enabled = module_req.enabled

        self.modules.get(module.id).enabled = module_req.enabled

    def update_modules(self, db: Session, module_req: ModuleBulkUpdateRequest):
        db_modules: List[models.Module] = (
            db.query(models.Module)
            .filter(models.Module.id.in_(module_req.modules))
            .all()
        )

        for db_module in db_modules:
            db_module.enabled = module_req.enabled

        for db_module in db_modules:
            self.modules.get(db_module.id).enabled = module_req.enabled

    def execute_module(
        self,
        module_id: str,
        params: Dict,
        ignore_language_version_check: bool = False,
        ignore_admin_check: bool = False,
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Execute the module.
        :param module_id: str
        :param params: the execution parameters
        :param user_id: the user executing the module
        :return: tuple with the response and an error message (if applicable)
        """
        module = self.get_by_id(module_id)

        if not module:
            return None, f"Module not found for id {module_id}"
        if not module.enabled:
            return None, "Cannot execute disabled module"

        cleaned_options, err = self._validate_module_params(
            module, params, ignore_language_version_check, ignore_admin_check
        )

        if err:
            return None, err

        # todo remove global obfuscate?
        module_data = self._generate_script(
            module,
            cleaned_options,
            self.main_menu.obfuscate,
            self.main_menu.obfuscateCommand,
        )
        if isinstance(module_data, tuple):
            (module_data, err) = module_data
        else:
            # Not all modules return a tuple. If they just return a single value,
            # we don't want to throw an unpacking error.
            err = None
        if not module_data or module_data == "":
            return None, err or "module produced an empty script"
        if not module_data.isascii():
            # This previously returned 'None, 'module source contains non-ascii characters'
            # Was changed in 4.3 to print a warning.
            log.warning(f"Module source for {module_id} contains non-ascii characters")

        if module.language == LanguageEnum.powershell:
            module_data = helpers.strip_powershell_comments(module_data)

        task_command = ""
        if module.language == LanguageEnum.csharp:
            task_command = "TASK_CSHARP"
        # build the appropriate task command and module data blob
        elif module.background:
            # if this module should be run in the background
            extension = module.output_extension
            if extension and extension != "":
                # if this module needs to save its file output to the server
                #   format- [15 chars of prefix][5 chars extension][data]
                save_file_prefix = module.name.split("/")[-1]
                module_data = (
                    save_file_prefix.rjust(15) + extension.rjust(5) + module_data
                )
                task_command = "TASK_CMD_JOB_SAVE"
            else:
                task_command = "TASK_CMD_JOB"

        else:
            # if this module is run in the foreground
            extension = module.output_extension
            if module.output_extension and module.output_extension != "":
                # if this module needs to save its file output to the server
                #   format- [15 chars of prefix][5 chars extension][data]
                save_file_prefix = module.name.split("/")[-1][:15]
                module_data = (
                    save_file_prefix.rjust(15) + extension.rjust(5) + module_data
                )
                task_command = "TASK_CMD_WAIT_SAVE"
            else:
                task_command = "TASK_CMD_WAIT"

        return {"command": task_command, "data": module_data}, None

    def _validate_module_params(
        self,
        module: PydanticModule,
        params: Dict[str, str],
        ignore_language_version_check: bool = False,
        ignore_admin_check: bool = False,
    ) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
        """
        Given a module and execution params, validate the input and return back a clean Dict for execution.
        :param module: PydanticModule
        :param params: the execution parameters
        :return: tuple with options and the error message (if applicable)
        """
        options = {}

        for option in module.options:
            if option.name in params:
                option_type = type(params[option.name])
                expected_option_type = type(option.value)
                if option_type != expected_option_type:
                    casted = safe_cast(params[option.name], expected_option_type)
                    if casted is None:
                        return (
                            None,
                            f"incorrect type for option {option.name}. Expected {expected_option_type} but got {option_type}",
                        )
                    else:
                        params[option.name] = casted
                if option.strict and params[option.name] not in option.suggested_values:
                    return (
                        None,
                        f"{option.name} must be set to one of the suggested values.",
                    )
                elif option.required and (
                    params[option.name] is None or params[option.name] == ""
                ):
                    return None, f"required listener option missing: {option.name}"
                if option.name_in_code:
                    options[option.name_in_code] = params[option.name]
                else:
                    options[option.name] = params[option.name]
            elif option.required:
                return None, f"required module option missing: {option.name}"

        # todo move generate_agent to a stager.
        if module.name == "generate_agent":
            return options, None

        # todo remove the rest of the v1 references
        session_id = params["Agent"]
        agent = self.main_menu.agents.get_agent_db(session_id)

        if not self.main_menu.agents.is_agent_present(session_id):
            return None, "invalid agent name"

        if not agent:
            return None, "invalid agent name"

        module_version = float(module.min_language_version or 0)
        agent_version = float(agent.language_version or 0)
        # check if the agent/module PowerShell versions are compatible
        if module_version > agent_version and not ignore_language_version_check:
            return (
                None,
                f"module requires language version {module_version} but agent running language version {agent_version}",
            )

        if module.needs_admin and not ignore_admin_check:
            # if we're running this module for all agents, skip this validation
            if not agent.high_integrity:
                return None, "module needs to run in an elevated context"

        return options, None

    def _generate_script(
        self,
        module: PydanticModule,
        params: Dict,
        obfuscate=False,
        obfuscate_command="",
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Generate the script to execute
        :param module: the execution parameters (already validated)
        :param params: the execution parameters
        :param obfuscate:
        :param obfuscate_command:
        :return: tuple containing the generated script and an error if it exists
        """
        if module.advanced.custom_generate:
            return module.advanced.generate_class.generate(
                self.main_menu, module, params, obfuscate, obfuscate_command
            )
        elif module.language == LanguageEnum.powershell:
            return self._generate_script_powershell(
                module, params, obfuscate, obfuscate_command
            )
        elif module.language == LanguageEnum.python:
            return self._generate_script_python(module, params)
        elif module.language == LanguageEnum.csharp:
            return self._generate_script_csharp(module, params)

    @staticmethod
    def _generate_script_python(
        module: PydanticModule, params: Dict
    ) -> Tuple[Optional[str], Optional[str]]:
        if module.script_path:
            script_path = os.path.join(
                empire_config.yaml.get("directories", {})["module_source"],
                module.script_path,
            )
            with open(script_path, "r") as stream:
                script = stream.read()
        else:
            script = module.script

        for key, value in params.items():
            if key.lower() != "agent" and key.lower() != "computername":
                script = script.replace("{{ " + key + " }}", value).replace(
                    "{{" + key + "}}", value
                )

        return script, None

    def _generate_script_powershell(
        self,
        module: PydanticModule,
        params: Dict,
        obfuscate=False,
        obfuscate_command="",
    ) -> Tuple[Optional[str], Optional[str]]:
        if module.script_path:
            script, err = self.get_module_source(
                module_name=module.script_path,
                obfuscate=obfuscate,
                obfuscate_command=obfuscate_command,
            )

            if err:
                return None, err
        else:
            if obfuscate:
                script = data_util.obfuscate(
                    installPath=self.main_menu.installPath,
                    psScript=module.script,
                    obfuscationCommand=obfuscate_command,
                )
            else:
                script = module.script

        script_end = f" {module.script_end} "
        option_strings = []

        # This is where the code goes for all the modules that do not have a custom generate function.
        for key, value in params.items():
            if key.lower() not in ["agent", "computername", "outputfunction"]:
                if value and value != "":
                    if value.lower() == "true":
                        # if we're just adding a switch
                        # wannabe mustache templating.
                        # If we want to get more advanced, we can import a library for it.
                        this_option = (
                            module.advanced.option_format_string_boolean.replace(
                                "{{ KEY }}", str(key)
                            ).replace("{{KEY}}", str(key))
                        )
                        option_strings.append(f"{this_option}")
                    else:
                        this_option = (
                            module.advanced.option_format_string.replace(
                                "{{ KEY }}", str(key)
                            )
                            .replace("{{KEY}}", str(key))
                            .replace("{{ VALUE }}", str(value))
                            .replace("{{VALUE}}", str(value))
                        )
                        option_strings.append(f"{this_option}")

        script_end = (
            script_end.replace("{{ PARAMS }}", " ".join(option_strings))
            .replace("{{PARAMS}}", " ".join(option_strings))
            .replace(
                "{{ OUTPUT_FUNCTION }}", params.get("OutputFunction", "Out-String")
            )
            .replace("{{OUTPUT_FUNCTION}}", params.get("OutputFunction", "Out-String"))
        )

        # obfuscate the invoke command and append to script
        script = self.finalize_module(
            script=script,
            script_end=script_end,
            obfuscate=obfuscate,
            obfuscation_command=obfuscate_command,
        )

        return script, None

    def _generate_script_csharp(
        self, module: PydanticModule, params: Dict
    ) -> Tuple[Optional[str], Optional[str]]:
        try:
            compiler = self.main_menu.pluginsv2.get_by_id("csharpserver")
            if not compiler.status == "ON":
                return None, "csharpserver plugin not running"
            file_name = compiler.do_send_message(module.compiler_yaml, module.name)
            if file_name == "failed":
                return None, "module compile failed"

            script_file = (
                self.main_menu.installPath
                + "/csharp/Covenant/Data/Tasks/CSharp/Compiled/"
                + (params["DotNetVersion"]).lower()
                + "/"
                + file_name
                + ".compiled"
            )
            param_string = ""
            for key, value in params.items():
                if key.lower() not in ["agent", "computername", "dotnetversion"]:
                    if value and value != "":
                        param_string += "," + value

            return f"{script_file}|{param_string}", None

        except Exception as e:
            log.error(f"dotnet compile error: {e}")
            return None, "dotnet compile error"

    def _load_modules(self, db: Session):
        """
        Load Empire modules.
        """
        root_path = f"{db.query(models.Config).first().install_path}/modules/"

        log.info(f"v2: Loading modules from: {root_path}")

        for root, dirs, files in os.walk(root_path):
            for filename in files:
                if not filename.lower().endswith(
                    ".yaml"
                ) and not filename.lower().endswith(".yml"):
                    continue

                file_path = os.path.join(root, filename)

                # don't load up any of the templates
                if fnmatch.fnmatch(filename, "*template.yaml"):
                    continue

                # instantiate the module and save it to the internal cache
                try:
                    with open(file_path, "r") as stream:
                        if file_path.lower().endswith(".covenant.yaml"):
                            yaml2 = yaml.safe_load(stream)
                            for covenant_module in yaml2:
                                # remove None values so pydantic can apply defaults
                                yaml_module = {
                                    k: v
                                    for k, v in covenant_module.items()
                                    if v is not None
                                }
                                self._load_module(db, yaml_module, root_path, file_path)
                        else:
                            yaml2 = yaml.safe_load(stream)
                            yaml_module = {
                                k: v for k, v in yaml2.items() if v is not None
                            }
                            self._load_module(db, yaml_module, root_path, file_path)
                except Exception as e:
                    log.warning(e)

    def _load_module(self, db: Session, yaml_module, root_path, file_path: str):
        # extract just the module name from the full path
        module_name = file_path.split(root_path)[-1][0:-5]

        if file_path.lower().endswith(".covenant.yaml"):
            cov_yaml_module = _convert_covenant_to_empire(yaml_module, file_path)
            module_name = f"{module_name[:-9]}/{cov_yaml_module['name']}"
            cov_yaml_module["id"] = self.slugify(module_name)
            my_model = PydanticModule(**cov_yaml_module)
        else:
            yaml_module["id"] = self.slugify(module_name)
            my_model = PydanticModule(**yaml_module)

        if my_model.advanced.custom_generate:
            if not os.path.exists(file_path[:-4] + "py"):
                raise Exception("No File to use for custom generate.")
            spec = importlib.util.spec_from_file_location(
                module_name + ".py", file_path[:-5] + ".py"
            )
            imp_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(imp_mod)
            my_model.advanced.generate_class = imp_mod.Module()
        elif my_model.script_path:
            if not os.path.exists(
                os.path.join(
                    empire_config.yaml.get("directories", {})["module_source"],
                    my_model.script_path,
                )
            ):
                raise Exception(
                    f"File provided in script_path does not exist: { module_name }"
                )
        elif my_model.script:
            pass
        else:
            raise Exception(
                "Must provide a valid script, script_path, or custom generate function"
            )

        mod = db.query(models.Module).filter(models.Module.id == my_model.id).first()

        if not mod:
            mod = models.Module(id=my_model.id, name=module_name, enabled=True)
            db.add(mod)

        self.modules[self.slugify(module_name)] = my_model
        self.modules[self.slugify(module_name)].enabled = mod.enabled

    def get_module_source(
        self, module_name: str, obfuscate: bool = False, obfuscate_command: str = ""
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Get the obfuscated/unobfuscated module source code.
        """
        try:
            if obfuscate:
                obfuscated_module_source = empire_config.yaml.get("directories", {})[
                    "obfuscated_module_source"
                ]
                module_path = os.path.join(obfuscated_module_source, module_name)
                # If pre-obfuscated module exists then return code
                if os.path.exists(module_path):
                    with open(module_path, "r") as f:
                        obfuscated_module_code = f.read()
                    return obfuscated_module_code, None

                # If pre-obfuscated module does not exist then generate obfuscated code and return it
                else:
                    module_source = empire_config.yaml.get("directories", {})[
                        "module_source"
                    ]
                    module_path = os.path.join(module_source, module_name)
                    with open(module_path, "r") as f:
                        module_code = f.read()
                    obfuscated_module_code = data_util.obfuscate(
                        installPath=self.main_menu.installPath,
                        psScript=module_code,
                        obfuscationCommand=obfuscate_command,
                    )
                    return obfuscated_module_code, None

            # Use regular/unobfuscated code
            else:
                module_source = empire_config.yaml.get("directories", {})[
                    "module_source"
                ]
                module_path = os.path.join(module_source, module_name)
                with open(module_path, "r") as f:
                    module_code = f.read()
                return module_code, None
        except:
            return None, f"[!] Could not read module source path at: {module_source}"

    def finalize_module(
        self,
        script: str,
        script_end: str,
        obfuscate: bool = False,
        obfuscation_command: str = "",
    ) -> str:
        """
        Combine script and script end with obfuscation if needed.
        """
        if obfuscate:
            script_end = data_util.obfuscate(
                self.main_menu.installPath,
                psScript=script_end,
                obfuscationCommand=obfuscation_command,
            )
        script += script_end
        script = data_util.keyword_obfuscation(script)
        return script

    @staticmethod
    def slugify(module_name: str):
        return module_name.lower().replace("/", "_")
