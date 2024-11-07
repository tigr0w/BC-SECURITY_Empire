import logging

from empire.client.src.EmpireCliState import state
from empire.client.src.menus.Menu import Menu
from empire.client.src.utils import table_util
from empire.client.src.utils.cli_util import command, register_cli_commands

log = logging.getLogger(__name__)


@register_cli_commands
class CredentialMenu(Menu):
    def __init__(self):
        super().__init__(display_name="credentials", selected="")

    def autocomplete(self):
        return self._cmd_registry + super().autocomplete()

    def get_completions(self, document, complete_event, cmd_line, word_before_cursor):
        yield from super().get_completions(
            document, complete_event, cmd_line, word_before_cursor
        )

    def on_enter(self):
        state.get_credentials()
        self.list()
        return True

    @command
    def list(self) -> None:
        """
        Get list of credentials

        Usage: list
        """
        cred_list = []
        for cred in state.get_credentials().values():
            cred_list.append(
                [
                    str(cred["id"]),
                    cred["credtype"],
                    cred["domain"],
                    cred["username"],
                    cred["host"],
                    cred["password"][:50],
                    cred["sid"],
                    cred["os"],
                ]
            )

        cred_list.insert(
            0,
            [
                "ID",
                "CredType",
                "Domain",
                "UserName",
                "Host",
                "Password/Hash",
                "SID",
                "OS",
            ],
        )

        table_util.print_table(cred_list, "Credentials")


credential_menu = CredentialMenu()
