from typing import Dict, List, Optional

from pydantic import BaseModel

from empire.server.api.v2.shared_dto import Author, CustomOptionSchema, to_value_type
from empire.server.common.plugins import Plugin


def domain_to_dto_plugin(plugin: Plugin, uid: str):
    options = dict(
        map(
            lambda x: (
                x[0],
                {
                    "description": x[1]["Description"],
                    "required": x[1]["Required"],
                    "value": x[1]["Value"],
                    "strict": x[1]["Strict"],
                    "suggested_values": x[1]["SuggestedValues"],
                    "value_type": to_value_type(x[1]["Value"], x[1].get("Type")),
                },
            ),
            plugin.options.items(),
        )
    )

    authors = list(
        map(
            lambda x: {
                "name": x["Name"],
                "handle": x["Handle"],
                "link": x["Link"],
            },
            plugin.info.get("Authors") or [],
        )
    )

    return Plugin(
        id=uid,
        name=plugin.info.get("Name"),
        authors=authors,
        description=plugin.info.get("Description"),
        category=plugin.info.get("Category"),
        comments=plugin.info.get("Comments"),
        techniques=plugin.info.get("Techniques"),
        software=plugin.info.get("Software"),
        options=options,
    )


class Plugin(BaseModel):
    id: str
    name: str
    authors: List[Author]
    description: str
    techniques: List[str] = []
    software: Optional[str]
    comments: List[str]
    options: Dict[str, CustomOptionSchema]


class Plugins(BaseModel):
    records: List[Plugin]


class PluginExecutePostRequest(BaseModel):
    options: Dict[str, str]


class PluginExecuteResponse(BaseModel):
    detail: str = ""
