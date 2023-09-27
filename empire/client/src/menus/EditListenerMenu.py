import logging

from empire.client.src.EmpireCliState import state
from empire.client.src.menus.UseMenu import UseMenu
from empire.client.src.utils.cli_util import command, register_cli_commands

log = logging.getLogger(__name__)


@register_cli_commands
class EditListenerMenu(UseMenu):
    def __init__(self):
        super().__init__(
            display_name="editlistener", selected="", record=None, record_options=None
        )

    def autocomplete(self):
        return self._cmd_registry + super().autocomplete()

    def get_completions(self, document, complete_event, cmd_line, word_before_cursor):
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

    def use(self, name: str) -> None:
        """
        Use the selected listener

        Usage: use <name>
        """
        if name not in state.listeners:
            return None

        self.selected = name
        listener = state.listeners[self.selected]
        self.record = state.get_listener_template(listener["template"])

        # Pull template and display current values for listener
        self.record_options = self.record["options"]
        for key, value in listener["options"].items():
            self.record_options[key]["value"] = value

    @command
    def kill(self) -> None:
        """
        Kill the selected listener

        Usage: kill
        """
        response = state.kill_listener(state.listeners[self.selected]["id"])
        if response.status_code == 204:
            log.info("Listener " + self.selected + " killed")
        elif "detail" in response:
            log.error(response["detail"])

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
        temp_record["enabled"] = False
        temp_record["id"] = state.listeners[self.selected]["id"]

        response = state.edit_listener(
            state.listeners[self.selected]["id"], temp_record
        )
        if "id" in response.keys():
            log.info("Listener " + temp_record["name"] + " edited")
        elif "detail" in response.keys():
            log.error(response["detail"])

        # re-enable listener
        temp_record["enabled"] = True
        response = state.edit_listener(
            state.listeners[self.selected]["id"], temp_record
        )
        if "id" in response.keys():
            log.info("Listener " + temp_record["name"] + " enabled")
        elif "detail" in response.keys():
            log.error("[!] Error: " + response["detail"])


edit_listener_menu = EditListenerMenu()
