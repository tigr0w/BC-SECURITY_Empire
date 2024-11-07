import logging

from empire.client.src.EmpireCliState import state
from empire.client.src.menus.Menu import Menu
from empire.client.src.utils import date_util, table_util
from empire.client.src.utils.cli_util import command, register_cli_commands

log = logging.getLogger(__name__)


@register_cli_commands
class AdminMenu(Menu):
    def __init__(self):
        super().__init__(display_name="admin", selected="")

    def autocomplete(self):
        return self._cmd_registry + super().autocomplete()

    def get_completions(self, document, complete_event, cmd_line, word_before_cursor):
        yield from super().get_completions(
            document, complete_event, cmd_line, word_before_cursor
        )

    def on_enter(self):
        self.user_id = state.get_user_me()["id"]
        return True

    @command
    def user_list(self) -> None:
        """
        Display all Empire user accounts

        Usage: user_list
        """
        users_list = []

        for user in state.get_users()["records"]:
            users_list.append(
                [
                    str(user["id"]),
                    user["username"],
                    str(user["is_admin"]),
                    str(user["enabled"]),
                    date_util.humanize_datetime(user["updated_at"]),
                ]
            )

        users_list.insert(0, ["ID", "Username", "Admin", "Enabled", "Last Logon Time"])

        table_util.print_table(users_list, "Users")


admin_menu = AdminMenu()
