from enum import Enum

from pydantic import BaseModel, constr

from empire.server.core.db import models

# Validate the string contains 1 colon
TagStr = constr(regex=r"^[^:]+:[^:]+$")

# Validate the string has no colons
TagStrNoColon = constr(regex=r"^[^:]+$")


class TagSourceFilter(str, Enum):
    listener = "listener"
    agent = "agent"
    agent_task = "agent_task"
    plugin_task = "plugin_task"
    download = "download"
    credential = "credential"


class Tag(BaseModel):
    id: int
    name: str
    value: str
    label: str
    color: str | None


class Tags(BaseModel):
    records: list[Tag]
    limit: int
    page: int
    total_pages: int
    total: int


class TagRequest(BaseModel):
    name: TagStrNoColon
    value: TagStrNoColon
    color: str | None


class TagOrderOptions(str, Enum):
    name = "name"
    created_at = "created_at"
    updated_at = "updated_at"


def domain_to_dto_tag(tag: models.Tag):
    return Tag(
        id=tag.id,
        name=tag.name,
        value=tag.value,
        label=f"{tag.name}:{tag.value}",
        color=tag.color,
    )
