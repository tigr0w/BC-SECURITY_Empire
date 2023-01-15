import logging
import string
import textwrap

from prompt_toolkit.completion import Completion

from empire.client.src.EmpireCliState import state
from empire.client.src.menus.Menu import Menu
from empire.client.src.utils import date_util, print_util, table_util
from empire.client.src.utils.autocomplete_util import (
    filtered_search_list,
    position_util,
)
from empire.client.src.utils.cli_util import command, register_cli_commands

log = logging.getLogger(__name__)


@register_cli_commands
class ListenerMenu(Menu):
    def __init__(self):
        super().__init__(display_name="listeners", selected="")

    def autocomplete(self):
        return self._cmd_registry + super().autocomplete()

    def get_completions(self, document, complete_event, cmd_line, word_before_cursor):
        if cmd_line[0] in ["kill", "options", "enable", "disable"] and position_util(
            cmd_line, 2, word_before_cursor
        ):
            for listener in filtered_search_list(
                word_before_cursor, state.listeners.keys()
            ):
                yield Completion(listener, start_position=-len(word_before_cursor))
        elif cmd_line[0] == "editlistener" and position_util(
            cmd_line, 2, word_before_cursor
        ):
            for listener in filtered_search_list(
                word_before_cursor, sorted(state.listeners.keys())
            ):
                yield Completion(listener, start_position=-len(word_before_cursor))

        yield from super().get_completions(
            document, complete_event, cmd_line, word_before_cursor
        )

    def on_enter(self):
        self.list()
        return True

    @command
    def list(self) -> None:
        """
        Get running/available listeners

        Usage: list
        """
        listener_list = list(
            map(
                lambda x: [
                    x["id"],
                    x["name"],
                    x["template"],
                    date_util.humanize_datetime(x["created_at"]),
                    x["enabled"],
                ],
                state.listeners.values(),
            )
        )
        listener_list.insert(0, ["ID", "Name", "Template", "Created At", "Enabled"])

        table_util.print_table(listener_list, "Listeners List")

    @command
    def options(self, listener_name: str) -> None:
        """
        Get option details for the selected listener

        Usage: options <listener_name>
        """
        if listener_name not in state.listeners:
            return None

        record_list = []
        for key, value in state.listeners[listener_name]["options"].items():
            name = key
            record_value = print_util.text_wrap(value.get("value", ""))
            required = print_util.text_wrap(value.get("required", ""))
            description = print_util.text_wrap(value.get("description", ""))
            record_list.append([name, record_value, required, description])

        record_list.insert(0, ["Name", "Value", "Required", "Description"])

        table_util.print_table(record_list, "Record Options")

    @command
    def kill(self, listener_name: str) -> None:
        """
        Kill the selected listener

        Usage: kill <listener_name>
        """
        response = state.kill_listener(state.listeners[listener_name]["id"])
        if response.status_code == 204:
            log.info("Listener " + listener_name + " killed")
        elif "detail" in response:
            log.error(response["detail"])

    @command
    def editlistener(self, listener_name: str) -> None:
        """
        Edit the selected listener

        Usage: editlistener <listener_name>
        """
        # Empty so the menu can see the option and usage
        pass


listener_menu = ListenerMenu()
