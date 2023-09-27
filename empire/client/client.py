import logging
import re
import shlex
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, get_type_hints

import urllib3
from docopt import docopt
from prompt_toolkit import HTML, PromptSession, shortcuts
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.patch_stdout import patch_stdout

from empire.arguments import args
from empire.client.src.bindings import bindings
from empire.client.src.EmpireCliConfig import empire_config
from empire.client.src.EmpireCliState import state
from empire.client.src.menus import Menu
from empire.client.src.menus.AdminMenu import admin_menu
from empire.client.src.menus.AgentMenu import agent_menu
from empire.client.src.menus.ChatMenu import chat_menu
from empire.client.src.menus.CredentialMenu import credential_menu
from empire.client.src.menus.EditListenerMenu import edit_listener_menu
from empire.client.src.menus.InteractMenu import interact_menu
from empire.client.src.menus.ListenerMenu import listener_menu
from empire.client.src.menus.MainMenu import main_menu
from empire.client.src.menus.PluginMenu import plugin_menu
from empire.client.src.menus.ProxyMenu import proxy_menu
from empire.client.src.menus.ShellMenu import shell_menu
from empire.client.src.menus.SponsorsMenu import sponsors_menu
from empire.client.src.menus.UseCredentialMenu import use_credential_menu
from empire.client.src.menus.UseListenerMenu import use_listener_menu
from empire.client.src.menus.UseModuleMenu import use_module_menu
from empire.client.src.menus.UsePluginMenu import use_plugin_menu
from empire.client.src.menus.UseStagerMenu import use_stager_menu
from empire.client.src.MenuState import menu_state
from empire.client.src.ShortcutHandler import shortcut_handler
from empire.client.src.utils import file_util, print_util
from empire.client.src.utils.autocomplete_util import (
    current_files,
    filtered_search_list,
)
from empire.client.src.utils.log_util import FileFormatter, MyFormatter

log = logging.getLogger(__name__)


class MyCustomCompleter(Completer):
    def __init__(self, empire_cli):
        self.empire_cli = empire_cli

    def get_completions(self, document, complete_event):
        word_before_cursor = document.get_word_before_cursor(WORD=True)

        try:
            cmd_line = list(
                map(lambda s: s.lower(), shlex.split(document.current_line))
            )
            if len(cmd_line) == 0:
                cmd_line.append("")
        except ValueError:
            pass
        else:
            if not state.connected:
                yield from self.empire_cli.menus["MainMenu"].get_completions(
                    document, complete_event, cmd_line, word_before_cursor
                )
            # These commands should be accessible anywhere.
            elif cmd_line[0] in ["uselistener"]:
                yield from self.empire_cli.menus["UseListenerMenu"].get_completions(
                    document, complete_event, cmd_line, word_before_cursor
                )
            elif cmd_line[0] in ["usestager"]:
                yield from self.empire_cli.menus["UseStagerMenu"].get_completions(
                    document, complete_event, cmd_line, word_before_cursor
                )
            elif cmd_line[0] in ["usemodule"]:
                yield from self.empire_cli.menus["UseModuleMenu"].get_completions(
                    document, complete_event, cmd_line, word_before_cursor
                )
            elif cmd_line[0] in ["interact"]:
                yield from self.empire_cli.menus["InteractMenu"].get_completions(
                    document, complete_event, cmd_line, word_before_cursor
                )
            elif cmd_line[0] in ["useplugin"]:
                yield from self.empire_cli.menus["UsePluginMenu"].get_completions(
                    document, complete_event, cmd_line, word_before_cursor
                )
            elif cmd_line[0] in ["usecredential"]:
                yield from self.empire_cli.menus["UseCredentialMenu"].get_completions(
                    document, complete_event, cmd_line, word_before_cursor
                )
            elif cmd_line[0] in ["resource"]:
                if len(cmd_line) > 1 and cmd_line[1] == "-p":
                    file = state.search_files()
                    if file:
                        yield Completion(file, start_position=-len(word_before_cursor))
                else:
                    for files in filtered_search_list(
                        word_before_cursor, current_files(state.directory["downloads"])
                    ):
                        yield Completion(
                            files,
                            display=files.split("/")[-1],
                            start_position=-len(word_before_cursor),
                        )
            else:
                # Menu specific commands
                yield from menu_state.current_menu.get_completions(
                    document, complete_event, cmd_line, word_before_cursor
                )


class CliExitException(BaseException):
    pass


class EmpireCli:
    def __init__(self) -> None:
        self.completer = MyCustomCompleter(self)
        self.menus: Dict[Menu] = {
            "MainMenu": main_menu,
            "ListenerMenu": listener_menu,
            "UseCredentialMenu": use_credential_menu,
            "UseListenerMenu": use_listener_menu,
            "EditListenerMenu": edit_listener_menu,
            "UseStagerMenu": use_stager_menu,
            "AgentMenu": agent_menu,
            "UseModuleMenu": use_module_menu,
            "InteractMenu": interact_menu,
            "ShellMenu": shell_menu,
            "CredentialMenu": credential_menu,
            "PluginMenu": plugin_menu,
            "UsePluginMenu": use_plugin_menu,
            "AdminMenu": admin_menu,
            "ChatMenu": chat_menu,
            "SponsorsMenu": sponsors_menu,
            "ProxyMenu": proxy_menu,
        }
        for menu in self.menus.values():
            state.register_menu(menu)

    @staticmethod
    def strip(options):
        return {re.sub("[^A-Za-z0-9 _]+", "", k): v for k, v in options.items()}

    @staticmethod
    def get_autoconnect_server() -> Optional[str]:
        """
        Looks for a server in the yaml marked for autoconnect.
        If one is not found, returns None
        :return: the name of the server to autoconnect
        """
        servers = empire_config.yaml.get("servers", {})
        autoserver = list(
            filter(lambda x: x[1].get("autoconnect") is True, servers.items())
        )

        if len(autoserver) > 0:
            return autoserver[0][0]

        return None

    @staticmethod
    def update_in_bg(session: PromptSession):
        while True:
            time.sleep(2)
            session.message = HTML(menu_state.current_menu.get_prompt())
            session.app.invalidate()

    def run_resource_file(self, session, resource):
        file_path = Path(resource)
        if not file_path.exists():
            log.error(f"File {file_path.name} does not exist.")
            return

        with file_path.open() as resource_file:
            log.info(f"Executing Resource File: {file_path.name}")
            for cmd in resource_file:
                with patch_stdout(raw=True):
                    try:
                        time.sleep(1)
                        text = session.prompt(
                            accept_default=True,
                            default=cmd.strip(),
                            mouse_support=empire_config.yaml.get(
                                "mouse-support", False
                            ),
                        )
                        cmd_line = list(shlex.split(text))
                        self.parse_command_line(text, cmd_line, resource_file=True)
                    except CliExitException:
                        return
                    except Exception:
                        log.error("Error parsing resource command: ", text)

        log.info(f"Finished executing resource file: {resource}")

    def main(self):
        setup_logging(args)

        if empire_config.yaml.get("suppress-self-cert-warning", True):
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        # Create some history first. (Easy for testing.)
        history = InMemoryHistory()
        history.append_string("help")
        history.append_string("uselistener http")
        history.append_string("listeners")
        history.append_string("main")
        history.append_string("connect -c localhost")

        print_util.loading()
        print_util.connect_message()

        session = PromptSession(
            key_bindings=bindings,
            history=history,
            completer=self.completer,
            complete_in_thread=True,
            bottom_toolbar=state.bottom_toolbar,
        )
        t = threading.Thread(target=self.update_in_bg, args=[session])
        t.daemon = True
        t.start()

        menu_state.push(main_menu)

        autoserver = self.get_autoconnect_server()
        if autoserver:
            log.info(f"Attempting to connect to server: {autoserver}")
            self.menus["MainMenu"].connect(autoserver, config=True)

        if args.resource:
            self.run_resource_file(session, args.resource)

        while True:
            try:
                with patch_stdout(raw=True):
                    text = session.prompt(
                        HTML(menu_state.current_menu.get_prompt()),
                        refresh_interval=None,
                        mouse_support=empire_config.yaml.get("mouse-support", False),
                    )

                    cmd_line = list(shlex.split(text))

                    if not cmd_line:
                        pass
                    elif cmd_line[0] == "resource":
                        if len(cmd_line) == 1:
                            log.error("[!] You must specify a resource file.")
                        else:
                            self.run_resource_file(session, cmd_line[1])

                    # cmd_line = list(map(lambda s: s.lower(), shlex.split(text)))
                    # TODO what to do about case sensitivity for parsing options.
                    self.parse_command_line(text, cmd_line)
            except KeyboardInterrupt:
                log.error("Type exit to quit")
            except ValueError as e:
                log.error(f"Error processing command: {e}")
            except EOFError:
                break  # Control-D pressed.
            except CliExitException:
                break

    def parse_command_line(self, text: str, cmd_line: List[str], resource_file=False):
        if len(cmd_line) == 0:
            return
        if not state.connected and not cmd_line[0] == "connect":
            if cmd_line[0] == "exit":
                choice = input(print_util.color("[>] Exit? [y/N] ", "red"))
                if choice.lower() == "y":
                    raise CliExitException
                else:
                    return
            else:
                return

        # Switch Menus
        if text.strip() == "main":
            state.get_modules()
            state.get_listeners()
            print_util.title(
                state.empire_version,
                f"{state.host}:{state.port}" if state.connected else "",
                len(state.modules),
                len(state.listeners),
                len(state.active_agents),
            )
            menu_state.push(self.menus["MainMenu"])
        elif text.strip() == "clear":
            shortcuts.clear()
        elif text.strip() == "listeners":
            menu_state.push(self.menus["ListenerMenu"])
        elif text.strip() == "chat":
            menu_state.push(self.menus["ChatMenu"])
        elif menu_state.current_menu_name == "ChatMenu":
            menu_state.current_menu.send_chat(text)
        elif text.strip() == "agents":
            menu_state.push(self.menus["AgentMenu"])
        elif text.strip() == "sponsors":
            menu_state.push(self.menus["SponsorsMenu"])
        elif text.strip() == "credentials":
            menu_state.push(self.menus["CredentialMenu"])
        elif text.strip() == "plugins":
            menu_state.push(self.menus["PluginMenu"])
        elif text.strip() == "admin":
            menu_state.push(self.menus["AdminMenu"])
        elif cmd_line[0] == "uselistener" and len(cmd_line) > 1:
            if cmd_line[1] in state.listener_types:
                menu_state.push(self.menus["UseListenerMenu"], selected=cmd_line[1])
            else:
                log.error(f"Listener not found: {cmd_line[1]}")
        elif cmd_line[0] == "usestager" and len(cmd_line) > 1:
            if cmd_line[1] in state.stagers:
                menu_state.push(self.menus["UseStagerMenu"], selected=cmd_line[1])
            else:
                log.error(f"Stager not found: {cmd_line[1]}")
        elif cmd_line[0] == "interact" and len(cmd_line) > 1:
            if cmd_line[1] in state.agents:
                menu_state.push(self.menus["InteractMenu"], selected=cmd_line[1])
            else:
                log.error(f"Agent not found: {cmd_line[1]}")
        elif cmd_line[0] == "useplugin" and len(cmd_line) > 1:
            if cmd_line[1] in state.plugins:
                menu_state.push(self.menus["UsePluginMenu"], selected=cmd_line[1])
            else:
                log.error(f"Plugin not found: {cmd_line[1]}")
        elif cmd_line[0] == "usecredential" and len(cmd_line) > 1:
            if cmd_line[1] in state.credentials or cmd_line[1] == "add":
                menu_state.push(self.menus["UseCredentialMenu"], selected=cmd_line[1])
            else:
                log.error(f"Credential not found: {cmd_line[1]}")
        elif cmd_line[0] == "usemodule" and len(cmd_line) > 1:
            if cmd_line[1] in state.modules:
                if menu_state.current_menu_name == "InteractMenu":
                    menu_state.push(
                        self.menus["UseModuleMenu"],
                        selected=cmd_line[1],
                        agent=menu_state.current_menu.selected,
                    )
                else:
                    menu_state.push(self.menus["UseModuleMenu"], selected=cmd_line[1])
            else:
                log.error(f"Module not found: {cmd_line[1]}")
        elif cmd_line[0] == "editlistener" and len(cmd_line) > 1:
            if menu_state.current_menu_name == "ListenerMenu":
                if cmd_line[1] in state.listeners:
                    menu_state.push(
                        self.menus["EditListenerMenu"], selected=cmd_line[1]
                    )
            else:
                log.error(f"Listener not found: {cmd_line[1]}")
        elif text.strip() == "shell":
            if menu_state.current_menu_name == "InteractMenu":
                menu_state.push(
                    self.menus["ShellMenu"], selected=menu_state.current_menu.selected
                )
            else:
                pass
        elif menu_state.current_menu_name == "ShellMenu":
            if text == "exit":
                menu_state.push(
                    self.menus["InteractMenu"],
                    selected=menu_state.current_menu.selected,
                )
            else:
                menu_state.current_menu.shell(menu_state.current_menu.selected, text)
        elif text.strip() == "proxy":
            if menu_state.current_menu_name == "InteractMenu":
                if menu_state.current_menu.agent_options["language"] not in [
                    "python",
                    "ironpython",
                ]:
                    log.error(
                        f'Agent proxies are not available in {menu_state.current_menu.agent_options["language"]} agents'
                    )
                    pass
                elif state.listeners[menu_state.current_menu.agent_options["listener"]][
                    "template"
                ] not in ["http", "http_hop", "redirector"]:
                    log.error(
                        f"Agent proxies are not available in {state.listeners[menu_state.current_menu.agent_options['listener']]['module']} listeners"
                    )
                else:
                    menu_state.push(
                        self.menus["ProxyMenu"],
                        selected=menu_state.current_menu.selected,
                    )
            else:
                pass
        elif text.strip() == "back":
            menu_state.pop()
        elif text.strip() == "exit":
            if resource_file:
                raise CliExitException
            choice = input(print_util.color("[>] Exit? [y/N] ", "red"))
            if choice.lower() == "y":
                raise CliExitException
            else:
                pass
        elif cmd_line[0] == "help" and len(cmd_line) > 1:
            func = None
            try:
                func = getattr(
                    menu_state.current_menu
                    if hasattr(menu_state.current_menu, cmd_line[1])
                    else self,
                    cmd_line[1],
                )
            except Exception:
                pass

            if func:
                print(func.__doc__)
        else:
            func = None
            try:
                func = getattr(
                    menu_state.current_menu
                    if hasattr(menu_state.current_menu, cmd_line[0])
                    else self,
                    cmd_line[0],
                )
            except Exception:
                pass

            if func:
                try:
                    # If the command is set, wrap the value in quotes so docopt
                    # doesn't interpret it as a parameter. Also concatenate all the words
                    # after the 3rd word for easier autofilling with suggested values that have spaces
                    # There may be a better way to do this.
                    if cmd_line[0] == "set":
                        if len(cmd_line) > 3:
                            cmd_line[2] = f'"{" ".join(cmd_line[2:])}"'
                            del cmd_line[3:]
                    args = self.strip(docopt(func.__doc__, argv=cmd_line[1:]))
                    new_args = {}
                    # todo casting for type hinted values?
                    for key in get_type_hints(func).keys():
                        if key != "return":
                            new_args[key] = args[key]
                    func(**new_args)
                except Exception as e:
                    log.error(e)
                    pass
                except SystemExit:
                    pass
            elif not func and menu_state.current_menu_name == "InteractMenu":
                if cmd_line[0] in shortcut_handler.get_names(
                    self.menus["InteractMenu"].agent_language
                ):
                    menu_state.current_menu.execute_shortcut(cmd_line[0], cmd_line[1:])


def setup_logging(args):
    if args.log_level:
        log_level = logging.getLevelName(args.log_level.upper())
    else:
        log_level = logging.getLevelName(empire_config.yaml["logging"]["level"].upper())

    logging_dir = empire_config.yaml["logging"]["directory"]
    log_dir = Path(logging_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    root_log_file = log_dir / "empire_client.log"

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    root_logger_stream_handler = logging.StreamHandler()
    root_logger_stream_handler.setFormatter(MyFormatter())
    root_logger_stream_handler.setLevel(log_level)
    root_logger.addHandler(root_logger_stream_handler)

    root_logger_file_handler = logging.FileHandler(root_log_file)
    root_logger_file_handler.setFormatter(FileFormatter())
    root_logger.addHandler(root_logger_file_handler)


def reset():
    # todo empire_config in the client should be converted to a class like the one in the server.
    download_dir = empire_config.yaml.get("directories", {}).get("downloads")
    if download_dir:
        file_util.remove_dir_contents(download_dir)
    stager_dir = empire_config.yaml.get("directories", {}).get("generated-stagers")
    if stager_dir:
        file_util.remove_dir_contents(stager_dir)


def start(args):
    if args.reset:
        choice = input(
            "\x1b[1;33m[>] Would you like to reset your Empire Client instance? [y/N]: \x1b[0m"
        )
        if choice.lower() == "y":
            reset()
            sys.exit()
    try:
        empire = EmpireCli()
        empire.main()
    finally:
        state.shutdown()
