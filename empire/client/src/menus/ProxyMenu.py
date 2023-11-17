import logging

from prompt_toolkit.completion import Completion

from empire.client.src.EmpireCliState import state
from empire.client.src.menus.UseMenu import UseMenu
from empire.client.src.utils import table_util
from empire.client.src.utils.autocomplete_util import (
    filtered_search_list,
    position_util,
)
from empire.client.src.utils.cli_util import command, register_cli_commands

log = logging.getLogger(__name__)


@register_cli_commands
class ProxyMenu(UseMenu):
    def __init__(self):
        super().__init__(display_name="", selected="")
        self.stop_threads = False

    def autocomplete(self):
        return self._cmd_registry + super().autocomplete()

    def get_completions(self, document, complete_event, cmd_line, word_before_cursor):
        if cmd_line[0] in ["set", "unset"] and position_util(
            cmd_line, 2, word_before_cursor
        ):
            for option in filtered_search_list(word_before_cursor, self.record_options):
                yield Completion(option, start_position=-len(word_before_cursor))
        elif cmd_line[0] == "set" and position_util(cmd_line, 3, word_before_cursor):
            if (
                len(cmd_line) > 1
                and len(self.suggested_values_for_option(cmd_line[1])) > 0
            ):
                for suggested_value in filtered_search_list(
                    word_before_cursor, self.suggested_values_for_option(cmd_line[1])
                ):
                    yield Completion(
                        suggested_value, start_position=-len(word_before_cursor)
                    )

        yield from super().get_completions(
            document, complete_event, cmd_line, word_before_cursor
        )

    def on_enter(self, **kwargs) -> bool:
        if "selected" not in kwargs:
            return False
        else:
            self.use(kwargs["selected"])
            return True

    def get_prompt(self) -> str:
        return f"(Empire: <ansired>{self.selected}</ansired>/<ansiblue>proxy</ansiblue>) > "

    def use(self, agent_name: str) -> None:
        """
        Use proxy

        Usage: proxy
        """
        try:
            self.record = state.get_proxy_info(agent_name)["proxy"]
            self.record_options = self.record["options"]
            if agent_name in state.agents.keys():
                self.selected = agent_name
                self.session_id = state.agents[self.selected]["session_id"]
                self.agent_options = state.agents[
                    agent_name
                ]  # todo rename agent_options
                self.agent_language = self.agent_options["language"]
                self.proxy_list = self.agent_options["proxy"]
                if not self.proxy_list:
                    self.proxy_list = []
                self.list()
        except Exception:
            log.error("Proxy menu failed to initialize")

    @command
    def add(self, position: int) -> None:
        """
        Tasks a specified agent to update proxy chain

        Usage: add_proxy [<position>]
        """
        self.agent_options = state.agents[self.session_id]
        if not self.proxy_list:
            self.proxy_list = []

        if position:
            self.proxy_list.insert(
                int(position),
                {
                    "proxytype": self.record_options["proxy_type"]["value"],
                    "addr": self.record_options["address"]["value"],
                    "port": int(self.record_options["port"]["value"]),
                },
            )
        else:
            self.proxy_list.append(
                {
                    "proxytype": self.record_options["proxy_type"]["value"],
                    "addr": self.record_options["address"]["value"],
                    "port": int(self.record_options["port"]["value"]),
                }
            )

        # print table of proxies
        self.list()

    @command
    def delete(self, position: int) -> None:
        """
        Tasks an the specified agent to remove proxy chain

        Usage: delete_proxy <position>
        """
        self.agent_options = state.agents[self.session_id]
        if not self.proxy_list:
            self.proxy_list = []

        self.proxy_list.pop(int(position))

        # print table of proxies
        self.list()

    @command
    def execute(self) -> None:
        """
        Tasks an the specified agent to update its proxy chain

        Usage: execute
        """
        if self.proxy_list:
            state.update_agent_proxy(self.session_id, self.proxy_list)
            log.info("Tasked agent to update proxy chain")
        else:
            log.error("No proxy chain to configure")

    @command
    def list(self) -> None:
        """
        Display list of current proxy chains

        Usage: list
        """
        proxies = [
            [
                self.proxy_list.index(x) + 1,
                x["addr"],
                x["port"],
                x["proxytype"],
            ]
            for x in self.proxy_list
        ]
        proxies.insert(0, ["Hop", "Address", "Port", "Proxy Type"])

        table_util.print_table(proxies, "Active Proxies")

    def suggested_values_for_option(self, option: str):
        try:
            lower = {k.lower(): v for k, v in self.record_options.items()}
            return lower.get(option, {}).get("suggested_values", [])
        except AttributeError:
            return []


proxy_menu = ProxyMenu()
