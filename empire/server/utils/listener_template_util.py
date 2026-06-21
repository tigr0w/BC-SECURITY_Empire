"""Pure helpers for loading listener templates from sibling YAML files.

A listener folder under ``empire/server/listeners/<name>/`` carries a
``<name>.yaml`` describing its metadata (``info``) and ``options``. These
functions convert that declarative YAML into the runtime dict shapes the
listener Python classes already expect (capitalized keys), so the loader and
tests share one conversion path. No DB access, no server state — give it a
path, get dicts back.
"""

from pathlib import Path
from typing import Any

import yaml

try:
    from yaml import CSafeLoader as Loader
except ImportError:  # pragma: no cover - falls back when libyaml is absent
    from yaml import SafeLoader as Loader


def convert_listener_options(options: list[dict]) -> dict[str, dict[str, Any]]:
    """Convert the lowercase YAML option list into the capitalized runtime dict.

    Unlike ``option_util.convert_module_options``, internal options are
    RETAINED — listeners read internal option values directly off
    ``self.options`` at generate time.
    """
    converted: dict[str, dict[str, Any]] = {}
    for option in options:
        converted[option["name"]] = {
            "Description": option.get("description", ""),
            "Required": option.get("required", False),
            "Value": option.get("value", ""),
            "SuggestedValues": option.get("suggested_values", []) or [],
            "Strict": option.get("strict", False),
            "Internal": option.get("internal", False),
            "DependsOn": option.get("depends_on", []) or [],
        }
        if "bypass_language" in option:
            converted[option["name"]]["BypassLanguage"] = option["bypass_language"]
        if "name_in_code" in option:
            converted[option["name"]]["NameInCode"] = option["name_in_code"]
    return converted


def _convert_authors(authors: list[dict]) -> list[dict]:
    return [
        {
            "Name": a.get("name", ""),
            "Handle": a.get("handle", ""),
            "Link": a.get("link", ""),
        }
        for a in (authors or [])
    ]


def load_listener_template_yaml(path: Path) -> dict[str, Any]:
    """Parse a listener YAML file into ``{"id", "info", "options"}``.

    Raises ``KeyError`` if the load-bearing ``id`` or ``display_name`` fields
    are missing (fail loudly rather than registering a half-built template).
    """
    raw = yaml.load(Path(path).read_text(), Loader=Loader)

    listener_id = raw["id"]
    display_name = raw["display_name"]

    info = {
        "Name": display_name,
        "Authors": _convert_authors(raw.get("authors", [])),
        "Description": raw.get("description", ""),
        "Comments": raw.get("comments", []) or [],
        "Software": raw.get("software", ""),
        "Techniques": raw.get("techniques", []) or [],
        "Tactics": raw.get("tactics", []) or [],
    }

    return {
        "id": listener_id,
        "info": info,
        "options": convert_listener_options(raw.get("options", [])),
    }
