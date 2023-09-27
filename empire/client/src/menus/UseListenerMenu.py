import logging

from prompt_toolkit.completion import Completion

from empire.client.src.EmpireCliState import state
from empire.client.src.menus.UseMenu import UseMenu
from empire.client.src.utils.autocomplete_util import (
    filtered_search_list,
    position_util,
)
from empire.client.src.utils.cli_util import command, register_cli_commands

log = logging.getLogger(__name__)


@register_cli_commands
class UseListenerMenu(UseMenu):
    def __init__(self):
        super().__init__(
            display_name="uselistener", selected="", record=None, record_options=None
        )

    def autocomplete(self):
        return self._cmd_registry + super().autocomplete()

    def get_completions(self, document, complete_event, cmd_line, word_before_cursor):
        if cmd_line[0] == "uselistener" and position_util(
            cmd_line, 2, word_before_cursor
        ):
            for listener in filtered_search_list(
                word_before_cursor, sorted(state.listener_types)
            ):
                yield Completion(listener, start_position=-len(word_before_cursor))

        yield from super().get_completions(
            document, complete_event, cmd_line, word_before_cursor
        )

    def on_enter(self, **kwargs) -> bool:
        if "selected" not in kwargs:
            return False
        else:
            self.use(kwargs["selected"])
            self.info()
            self.options()
            return True

    def use(self, module: str) -> None:
        """
        Use the selected listener

        Usage: use <module>
        """
        if module in state.listener_types:
            self.selected = module
            self.record = state.get_listener_options(self.selected)
            self.record_options = self.record["options"]

    @command
    def execute(self):
        """
        Create the current listener

        Usage: execute
        """
        # todo validation and error handling
        # todo alias start to execute and generate
        # Hopefully this will force us to provide more info in api errors ;)
        post_body = {}
        temp_record = {}
        for key in self.record_options.keys():
            post_body[key] = self.record_options[key]["value"]

        temp_record["options"] = post_body
        temp_record["name"] = post_body["Name"]
        temp_record["template"] = self.record["id"]

        response = state.create_listener(temp_record)
        if "id" in response.keys():
            return
        elif "detail" in response.keys():
            log.error(response["detail"])

    @command
    def generate(self):
        """
        Create the current listener

        Usage: generate
        """
        self.execute()


use_listener_menu = UseListenerMenu()
