from pydantic import BaseModel

from empire.server.api.v2.shared_dto import (
    Author,
    CustomOptionSchema,
    coerced_dict,
    to_value_type,
)
from empire.server.core.plugins import BasePlugin


def domain_to_dto_plugin(plugin: BasePlugin, db):
    options = {
        x[0]: {
            "description": x[1]["Description"],
            "required": x[1]["Required"],
            "value": x[1]["Value"],
            "strict": x[1]["Strict"],
            "suggested_values": x[1]["SuggestedValues"],
            "value_type": to_value_type(x[1]["Value"], x[1].get("Type")),
        }
        for x in plugin.options.items()
    }

    return Plugin(
        id=plugin.info.name,
        name=plugin.info.name,
        authors=[a.model_dump() for a in plugin.info.authors],
        description=plugin.info.description,
        comments=plugin.info.comments,
        techniques=plugin.info.techniques,
        software=plugin.info.software,
        options=options,
        enabled=plugin.enabled,
    )


class Plugin(BaseModel):
    id: str
    name: str
    authors: list[Author]
    description: str
    techniques: list[str] = []
    software: str | None = None
    comments: list[str]
    options: dict[str, CustomOptionSchema]
    enabled: bool


class Plugins(BaseModel):
    records: list[Plugin]


class PluginExecutePostRequest(BaseModel):
    options: coerced_dict


class PluginExecuteResponse(BaseModel):
    detail: str = ""


class PluginUpdateRequest(BaseModel):
    enabled: bool
