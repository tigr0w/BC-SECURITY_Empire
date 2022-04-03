from typing import Dict, List, Optional

from pydantic import BaseModel

from empire.server.common.plugins import Plugin
from empire.server.v2.api.shared_dto import CustomOptionSchema, to_value_type


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
                    "value_type": to_value_type(x[1]["Value"]),
                },
            ),
            plugin.options.items(),
        )
    )

    return Plugin(
        id=uid,
        name=plugin.info.get("Name"),
        authors=plugin.info.get("Authors"),
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
    authors: List[str]
    description: str
    techniques: List[str] = []
    software: Optional[str]
    comments: List[str]
    options: Dict[str, CustomOptionSchema]


class Plugins(BaseModel):
    records: List[Plugin]


class PluginExecutePostRequest(BaseModel):
    options: Dict[str, str]
