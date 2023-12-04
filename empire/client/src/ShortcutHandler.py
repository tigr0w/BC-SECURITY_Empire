import json
import logging

from empire.client.src.EmpireCliConfig import empire_config
from empire.client.src.Shortcut import Shortcut

log = logging.getLogger(__name__)


class ShortcutHandler:
    """
    Handler class to get shortcuts.
    """

    def __init__(self):
        shortcuts_raw = empire_config.yaml.get("shortcuts", {})
        python: dict[str, Shortcut] = {}
        ironpython: dict[str, Shortcut] = {}
        powershell: dict[str, Shortcut] = {}
        csharp: dict[str, Shortcut] = {}
        for key, value in shortcuts_raw["python"].items():
            try:
                value["name"] = key
                python[key] = Shortcut.from_json(json.loads(json.dumps(value)))
            except TypeError:
                log.error(f"Could not parse shortcut: {key}")
        for key, value in shortcuts_raw["ironpython"].items():
            try:
                value["name"] = key
                ironpython[key] = Shortcut.from_json(json.loads(json.dumps(value)))
            except TypeError:
                log.error(f"Could not parse shortcut: {key}")
        for key, value in shortcuts_raw["powershell"].items():
            try:
                value["name"] = key
                powershell[key] = Shortcut.from_json(json.loads(json.dumps(value)))
            except TypeError:
                log.error(f"Could not parse shortcut: {key}")
        for key, value in shortcuts_raw["csharp"].items():
            try:
                value["name"] = key
                csharp[key] = Shortcut.from_json(json.loads(json.dumps(value)))
            except TypeError:
                log.error(f"Could not parse shortcut: {key}")
        self.shortcuts: dict[str, dict[str, Shortcut]] = {
            "python": python,
            "powershell": powershell,
            "ironpython": ironpython,
            "csharp": csharp,
        }

    def get(self, language: str, name: str) -> Shortcut:
        return self.shortcuts.get(language, {}).get(name)

    def get_names(self, language: str) -> list[str]:
        return list(self.shortcuts.get(language, {}).keys())


shortcut_handler = ShortcutHandler()
