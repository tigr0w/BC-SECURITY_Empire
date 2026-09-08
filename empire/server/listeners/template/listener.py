import os
import secrets
import time

# Empire imports
from empire.server.common import helpers
from empire.server.core.exceptions import ListenerValidationException
from empire.server.utils import data_util


class Listener:
    def __init__(self, mainMenu):
        self.mainMenu = mainMenu
        self.thread = None

    def post_init(self):
        # metadata (info) and options come from the sibling template.yaml; only
        # dynamic defaults that can't be expressed declaratively belong here.
        self.options["Host"]["Value"] = f"http://{helpers.lhost()}"

        # optional/specific for this module

        # set the default staging key to the controller db default
        self.options["StagingKey"]["Value"] = str(
            data_util.get_config("staging_key")[0]
        )

    def default_response(self):
        """
        If there's a default response expected from the server that the client needs to ignore,
        (i.e. a default HTTP page), put the generation here.
        """
        print(
            helpers.color(
                "[!] default_response() not implemented for listeners/template"
            )
        )
        return ""

    def validate_options(self) -> None:
        """
        Validate all options for this listener.
        """

        for key in self.options:
            if self.options[key]["Required"] and (
                str(self.options[key]["Value"]).strip() == ""
            ):
                raise ListenerValidationException(f'Option "{key}" is required.')

    def generate_launcher(
        self,
        encode=True,
        obfuscate=False,
        obfuscation_command="",
        user_agent="default",
        proxy="default",
        proxy_creds="default",
        language=None,
        listener_name=None,
        bypasses: list[str] | None = None,
    ):
        """
        Generate a basic launcher for the specified listener.
        """
        bypasses = [] if bypasses is None else bypasses

        if not language:
            print(
                helpers.color(
                    "[!] listeners/template generate_launcher(): no language specified!"
                )
            )
            return None

        active_listener = self
        # extract the set options for this instantiated listener
        listenerOptions = active_listener.options

        host = listenerOptions["Host"]["Value"]
        _stagingKey = listenerOptions["StagingKey"]["Value"]
        profile = listenerOptions["DefaultProfile"]["Value"]
        uris = [a.strip("/") for a in profile.split("|")[0].split(",")]
        stage0 = secrets.choice(uris)
        _launchURI = f"{host}/{stage0}"

        if language.startswith("po"):
            # PowerShell
            return ""

        if language.startswith("py"):
            # Python
            return ""

        print(
            helpers.color(
                "[!] listeners/template generate_launcher(): invalid language specification: only 'powershell' and 'python' are current supported for this module."
            )
        )
        return None

    def generate_stager(
        self,
        listenerOptions,
        encode=False,
        encrypt=True,
        obfuscate=False,
        obfuscation_command="",
        language=None,
    ):
        """
        If you want to support staging for the listener module, generate_stager must be
        implemented to return the stage1 key-negotiation stager code.
        """
        print(
            helpers.color(
                "[!] generate_stager() not implemented for listeners/template"
            )
        )
        return ""

    def generate_agent(
        self, listenerOptions, language=None, obfuscate=False, obfuscation_command=""
    ):
        """
        If you want to support staging for the listener module, generate_agent must be
        implemented to return the actual staged agent code.
        """
        print(
            helpers.color("[!] generate_agent() not implemented for listeners/template")
        )
        return ""

    def generate_comms(self, listenerOptions, language=None):
        """
        Generate just the agent communication code block needed for communications with this listener.
        This is so agents can easily be dynamically updated for the new listener.

        This should be implemented for the module.
        """

        if not language:
            print(
                helpers.color(
                    "[!] listeners/template generate_comms(): no language specified!"
                )
            )
            return None

        if language.lower() == "powershell":
            updateServers = """
                $Script:ControlServers = @("{}");
                $Script:ServerIndex = 0;
            """.format(listenerOptions["Host"]["Value"])

            getTask = """
                $script:GetTask = {


                }
            """

            sendMessage = """
                $script:SendMessage = {
                    param($Packets)

                    if($Packets) {

                    }
                }
            """

            return (
                updateServers
                + getTask
                + sendMessage
                + "\n'New agent comms registered!'"
            )

        if language.lower() == "python":
            # send_message()
            return None

        print(
            helpers.color(
                "[!] listeners/template generate_comms(): invalid language specification, only 'powershell' and 'python' are current supported for this module."
            )
        )
        return None

    def start_server(self):
        pass

    def start(self):
        """
        If a server component needs to be started, implement the kick off logic
        here and the actual server code in another function to facilitate threading
        (i.e. start_server() in the http listener).
        """
        listenerOptions = self.options
        self.thread = helpers.KThread(target=self.start_server, args=(listenerOptions,))
        self.thread.daemon = True
        self.thread.start()
        time.sleep(0.1 if os.environ.get("TEST_MODE") else 1)
        # returns True if the listener successfully started, false otherwise
        return self.thread.is_alive()

    def shutdown(self):
        """
        If a server component was started, implement the logic that kills the particular
        named listener here.
        """
        pass
