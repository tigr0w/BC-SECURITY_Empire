import logging
import subprocess
import textwrap
import time

from prompt_toolkit import HTML
from prompt_toolkit.completion import Completion

from empire.client.src.EmpireCliState import state
from empire.client.src.menus.Menu import Menu
from empire.client.src.utils import print_util, table_util
from empire.client.src.utils.autocomplete_util import (
    filtered_search_list,
    position_util,
)
from empire.client.src.utils.cli_util import command, register_cli_commands

log = logging.getLogger(__name__)


@register_cli_commands
class InteractMenu(Menu):
    def __init__(self):
        super().__init__(display_name="", selected="")
        self.agent_options = {}
        self.agent_language = ""
        self.session_id = ""

    def autocomplete(self):
        return self._cmd_registry + super().autocomplete()

    def get_completions(self, document, complete_event, cmd_line, word_before_cursor):
        if cmd_line[0] in ["interact"] and position_util(
            cmd_line, 2, word_before_cursor
        ):
            active_agents = [
                a["name"]
                for a in filter(lambda a: a["stale"] is not True, state.agents.values())
            ]
            for agent in filtered_search_list(word_before_cursor, active_agents):
                yield Completion(agent, start_position=-len(word_before_cursor))
        elif cmd_line[0] in ["display"] and position_util(
            cmd_line, 2, word_before_cursor
        ):
            for property_name in filtered_search_list(
                word_before_cursor, self.agent_options
            ):
                yield Completion(property_name, start_position=-len(word_before_cursor))
        elif cmd_line[0] in ["view"]:
            tasks = state.get_agent_tasks(self.session_id, 100)
            tasks = {str(x["id"]): x for x in tasks["records"]}

            for task_id in filtered_search_list(word_before_cursor, tasks.keys()):
                full = tasks[task_id]
                help_text = print_util.truncate(
                    f"{full.get('input', '')[:30]}, {full.get('username', '')}",
                    width=75,
                )
                yield Completion(
                    task_id,
                    display=HTML(f"{full['id']} <purple>({help_text})</purple>"),
                    start_position=-len(word_before_cursor),
                )
        yield from super().get_completions(
            document, complete_event, cmd_line, word_before_cursor
        )

    def on_enter(self, **kwargs) -> bool:
        if "selected" not in kwargs:
            return False
        else:
            self.use(kwargs["selected"])
            self.display_cached_results()
            return True

    def get_prompt(self) -> str:
        joined = "/".join([self.display_name, self.name]).strip("/")
        return f"(Empire: <ansired>{joined}</ansired>) > "

    def display_cached_results(self) -> None:
        """
        Print the task results for the all the results that have been received for this agent.
        """
        task_results = state.cached_agent_results.get(self.session_id, {})
        for key, value in task_results.items():
            log.info("Task " + str(key) + " results received")
            print(value)

        state.cached_agent_results.get(self.session_id, {}).clear()

    def use(self, agent_name: str) -> None:
        """
        Use the selected agent

        Usage: use <agent_name>
        """
        state.get_agents()
        if agent_name in state.agents:
            self.name = agent_name
            self.selected = state.agents[agent_name]["session_id"]
            self.session_id = state.agents[agent_name]["session_id"]
            self.agent_options = state.agents[agent_name]  # todo rename agent_options
            self.agent_language = self.agent_options["language"]

    @command
    def shell(self, shell_cmd: str, literal: bool = False) -> None:
        """
        Tasks the specified agent to execute a shell command.

        Usage: shell [--literal / -l] <shell_cmd>

        Options:
            --literal -l    Interpret the shell command literally. This will ensure that aliased
                            commands such as whoami or ps do not execute the built-in agent aliases.
        """
        literal = bool(literal)  # docopt parses into 0/1
        response = state.agent_shell(self.session_id, shell_cmd, literal)
        if "status" in response:
            log.info(
                "Tasked " + self.session_id + " to run Task " + str(response["id"])
            )

    @command
    def sysinfo(self) -> None:
        """
        Tasks the specified agent update sysinfo.

        Usage: sysinfo
        """
        response = state.sysinfo(self.session_id)
        if "status" in response:
            log.info(
                "Tasked " + self.session_id + " to run Task " + str(response["id"])
            )

    @command
    def info(self) -> None:
        """
        Display agent info.

        Usage: info
        """
        agent_list = []
        for key, value in self.agent_options.items():
            if isinstance(value, int):
                value = str(value)
            if value is None:
                value = ""
            if key not in ["taskings", "results"]:
                temp = [key, "\n".join(textwrap.wrap(str(value), width=45))]
                agent_list.append(temp)

        table_util.print_table(agent_list, "Agent Options")

    @command
    def help(self):
        """
        Display the help menu for the current menu

        Usage: help
        """
        help_list = []
        for name in self._cmd_registry:
            try:
                description = print_util.text_wrap(
                    getattr(self, name).__doc__.split("\n")[1].lstrip(), width=35
                )
                usage = print_util.text_wrap(
                    getattr(self, name).__doc__.split("\n")[3].lstrip()[7:], width=35
                )
                help_list.append([name, description, usage])
            except Exception:
                continue

        help_list.insert(0, ["Name", "Description", "Usage"])
        table_util.print_table(help_list, "Help Options")

    @command
    def history(self, number_tasks: int):
        """
        Display last number of task results received.

        Usage: history [<number_tasks>]
        """
        if not number_tasks:
            number_tasks = 5

        response = state.get_agent_tasks(self.session_id, str(number_tasks))

        if "records" in response:
            tasks = response["records"]
            for task in tasks:
                if task.get("output"):
                    log.info(f'Task {task["id"]} results received')
                    for line in task.get("output", "").split("\n"):
                        print(print_util.color(line))
                else:
                    log.error(f'Task {task["id"]} No tasking results received')
        elif "detail" in response:
            log.error(response["detail"])

    @command
    def view(self, task_id: str):
        """
        View specific task and result

        Usage: view <task_id>
        """
        task = state.get_agent_task(self.session_id, task_id)
        record_list = []
        record_list.append([print_util.color("ID", "blue"), task["id"]])
        record_list.append([print_util.color("Module", "blue"), task["module_name"]])
        record_list.append([print_util.color("Status", "blue"), task["status"]])
        record_list.append([print_util.color("Input", "blue"), task["input"]])

        table_util.print_table(
            record_list,
            "View Task",
            colored_header=False,
            borders=False,
            end_space=False,
        )
        print(print_util.color(" Output", "blue"))
        if task["output"]:
            for line in task["output"].split("\n"):
                print(print_util.color(line))

    @command
    def vnc_client(self, address: str, port: str, password: str) -> None:
        """
        Launch a VNC client to a remote server

        Usage: vnc_client <address> <port> <password>
        """
        vnc_cmd = [
            "python3",
            state.install_path + "/src/utils/vnc_util.py",
            address,
            port,
            password,
        ]
        self.vnc_proc = subprocess.Popen(
            vnc_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

    @command
    def vnc(self) -> None:
        """
        Launch a VNC server on the agent and spawn a VNC client

        Usage: vnc
        """
        module_options = dict.copy(state.modules["csharp_vnc_vncserver"]["options"])
        post_body = {}
        post_body["options"] = {}

        for key in module_options:
            post_body["options"][key] = str(module_options[key]["value"])

        post_body["module_id"] = "csharp_vnc_vncserver"
        response = state.execute_module(self.session_id, post_body)

        if "id" in response:
            log.info("Tasked " + self.selected + " to run Task " + str(response["id"]))
        elif "detail" in response:
            log.error(response["detail"])
            return

        log.info("Starting VNC server...")
        time.sleep(5)

        vnc_cmd = [
            "python3",
            state.install_path + "/src/utils/vnc_util.py",
            self.agent_options["internal_ip"],
            module_options["Port"]["value"],
            module_options["Password"]["value"],
        ]
        self.vnc_proc = subprocess.Popen(
            vnc_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

    @command
    def jobs(self) -> None:
        """
        View list of active jobs

        Usage: jobs
        """
        response = state.view_jobs(self.session_id)
        if "id" in response:
            print(
                print_util.color(
                    "[*] Tasked " + self.selected + " to retrieve active jobs"
                )
            )

        elif "detail" in response:
            print(print_util.color("[!] Error: " + response["detail"]))
            return

    @command
    def kill_job(self, task_id: int) -> None:
        """
        Kill an active jobs

        Usage: kill_job <task_id>
        """
        response = state.kill_job(self.session_id, task_id)
        if "id" in response:
            print(
                print_util.color(
                    "[*] Tasked " + self.selected + f" to kill task {task_id!s}"
                )
            )

        elif "detail" in response:
            print(print_util.color("[!] Error: " + response["detail"]))
            return


interact_menu = InteractMenu()
