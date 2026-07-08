from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, StringConstraints

from empire.server.core.db import models

# A tag name: non-empty, <=255 chars.
TagName = Annotated[str, StringConstraints(min_length=1, max_length=255)]

# A hex color: only the valid CSS forms #rgb, #rgba, #rrggbb, #rrggbbaa (3, 4, 6,
# or 8 hex digits — NOT 5 or 7). Fits the tags.color String(12) column and rejects
# junk at the API boundary with a clean 422.
HexColor = Annotated[
    str,
    StringConstraints(pattern=r"^#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$"),
]


class TagSourceFilter(StrEnum):
    listener = "listener"
    agent = "agent"
    agent_task = "agent_task"
    plugin_task = "plugin_task"
    download = "download"
    credential = "credential"


class Tag(BaseModel):
    id: int
    name: str
    color: str
    description: str | None = None


class TagWithUsage(Tag):
    usage_count: int


class Tags(BaseModel):
    records: list[TagWithUsage]
    limit: int
    page: int
    total_pages: int
    total: int


class TagAttachRequest(BaseModel):
    """Attach an existing tag to an entity by id. Create tags first via
    POST /api/v2/tags."""

    tag_id: int


class TagCreateRequest(BaseModel):
    """Create a registry tag (POST /api/v2/tags). ``name`` is required."""

    name: TagName
    color: HexColor | None = None
    description: str | None = None


class TagUpdateRequest(BaseModel):
    """Partial-update a registry tag (PUT /api/v2/tags/{id}).

    Omitted/None fields are left unchanged — ``name`` may be omitted to recolor or
    edit the description only (so color/description cannot be cleared back to NULL
    via this endpoint).
    """

    name: TagName | None = None
    color: HexColor | None = None
    description: str | None = None


class TagOrderOptions(StrEnum):
    name = "name"
    created_at = "created_at"
    updated_at = "updated_at"


def domain_to_dto_tag(tag: models.Tag) -> Tag:
    return Tag(
        id=tag.id,
        name=tag.name,
        color=tag.color,
        description=tag.description,
    )


def domain_to_dto_tag_with_usage(tag: models.Tag, usage_count: int) -> TagWithUsage:
    return TagWithUsage(**domain_to_dto_tag(tag).model_dump(), usage_count=usage_count)
