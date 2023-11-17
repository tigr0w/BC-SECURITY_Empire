import logging

from empire.client.src.utils import print_util

log = logging.getLogger(__name__)


# https://yzhong-cs.medium.com/serialize-and-deserialize-complex-json-in-python-205ecc636caa
class ShortcutParam:
    def __init__(self, name: str, dynamic: bool = False, value: str | None = ""):
        self.name = name
        self.dynamic = dynamic
        self.value = value

    @classmethod
    def from_json(cls, data):
        return cls(**data)


class Shortcut:
    def __init__(
        self,
        name: str,
        module: str | None = None,
        shell: str | None = None,
        params: list[ShortcutParam] = None,
    ):
        if not module and not shell:
            log.error("Shortcut must have either a module or shell command")
            raise TypeError

        self.name = name
        self.shell = None if not shell else shell
        self.module = module
        self.params = [] if not params else params

    def get_dynamic_params(self) -> list[ShortcutParam]:
        return list(filter(lambda x: x.dynamic, self.params))

    def get_dynamic_param_names(self) -> list[str]:
        return [x.name for x in self.get_dynamic_params()]

    def get_static_params(self) -> list[ShortcutParam]:
        return list(filter(lambda x: not x.dynamic, self.params))

    def get_static_param_names(self) -> list[str]:
        return [x.name for x in self.get_static_params()]

    def get_param(self, name: str) -> ShortcutParam | None:
        param = None
        for p in self.params:
            if p.name == name:
                param = p
                break

        return param

    def get_usage_string(self) -> str:
        usage = f"{self.name} "
        params = self.get_dynamic_param_names()
        for param in params:
            usage += f"<{param}> "

        return usage

    def get_help_description(self) -> str:
        if self.shell:
            return print_util.text_wrap(
                f"Tasks an agent to run the shell command '{self.shell}'"
            )

        module = self.module
        default_params = [f"{x.name}: {x.value}" for x in self.get_static_params()]
        description = f"Tasks the agent to run module {module}."
        if len(default_params) > 0:
            description += " Default parameters include:\n"
            description += "\n".join(default_params)

        return print_util.text_wrap(description)

    @classmethod
    def from_json(cls, data):
        if "params" not in data or data["params"] is None:
            data["params"] = []
        else:
            data["params"] = list(map(ShortcutParam.from_json, data["params"]))
        return cls(**data)
