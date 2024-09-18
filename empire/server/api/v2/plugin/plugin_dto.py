from typing import Any

from pydantic import BaseModel

from empire.server.api.v2.shared_dto import (
    Author,
    CustomOptionSchema,
    coerced_dict,
    to_value_type,
)
from empire.server.core.plugins import BasePlugin


def domain_to_dto_plugin(plugin: BasePlugin, db):
    execution_options = {
        x[0]: {
            "description": x[1]["Description"],
            "required": x[1]["Required"],
            "value": x[1]["Value"],
            "strict": x[1]["Strict"],
            "suggested_values": x[1]["SuggestedValues"],
            "value_type": to_value_type(x[1]["Value"], x[1].get("Type")),
            "depends_on": x[1]["Depends_on"] if x[1]["Depends_on"] is not None else [],
            "internal": x[1]["Internal"] if x[1]["Internal"] is not None else False,
        }
        for x in plugin.execution_options.items()
    }

    settings_options = {
        x[0]: {
            "description": x[1]["Description"],
            "editable": x[1].get("Editable", True),
            "required": x[1]["Required"],
            "value": x[1]["Value"],
            "strict": x[1]["Strict"],
            "suggested_values": x[1]["SuggestedValues"],
            "value_type": to_value_type(x[1]["Value"], x[1].get("Type")),
            "depends_on": x[1]["Depends_on"] if x[1]["Depends_on"] is not None else [],
            "internal": x[1]["Internal"] if x[1]["Internal"] is not None else False,
        }
        for x in plugin.settings_options.items()
    }

    return Plugin(
        id=plugin.info.name,
        name=plugin.info.name,
        authors=[a.model_dump() for a in plugin.info.authors],
        description=plugin.info.description,
        comments=plugin.info.comments,
        techniques=plugin.info.techniques,
        software=plugin.info.software,
        execution_options=execution_options,
        settings_options=settings_options,
        current_settings=plugin.current_settings(db),
        enabled=plugin.enabled,
        execution_enabled=plugin.execution_enabled,
    )


class Plugin(BaseModel):
    id: str
    name: str
    authors: list[Author]
    description: str
    techniques: list[str] = []
    software: str | None = None
    comments: list[str]
    execution_options: dict[str, CustomOptionSchema]
    settings_options: dict[str, CustomOptionSchema]
    current_settings: dict[str, Any]
    enabled: bool
    execution_enabled: bool


class Plugins(BaseModel):
    records: list[Plugin]


class PluginExecutePostRequest(BaseModel):
    options: coerced_dict


class PluginExecuteResponse(BaseModel):
    detail: str = ""


class PluginUpdateRequest(BaseModel):
    enabled: bool


class PluginInstallGitRequest(BaseModel):
    url: str
    ref: str | None = None
    subdirectory: str | None = None
