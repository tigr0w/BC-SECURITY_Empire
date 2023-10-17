from typing import Dict

from empire.server.core.module_models import EmpireModule


class Module:
    @staticmethod
    def generate(
        main_menu,
        module: EmpireModule,
        params: Dict,
        obfuscate: bool = False,
        obfuscation_command: str = "",
    ):
        max_size = params["MaxSize"]
        trace_file = params["TraceFile"]
        persistent = params["Persistent"]
        stop_trace = params["StopTrace"]

        if stop_trace.lower() == "true":
            script = "netsh trace stop"

        else:
            script = "netsh trace start capture=yes traceFile=%s" % (trace_file)

            if max_size != "":
                script += " maxSize=%s" % (max_size)

            if persistent != "":
                script += " persistent=yes"

        script = main_menu.modulesv2.finalize_module(
            script=script,
            script_end="",
            obfuscate=obfuscate,
            obfuscation_command=obfuscation_command,
        )
        return script
