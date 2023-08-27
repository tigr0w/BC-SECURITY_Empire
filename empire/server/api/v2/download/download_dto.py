from datetime import datetime
from enum import Enum
from typing import List

from pydantic import BaseModel

from empire.server.api.v2.tag.tag_dto import Tag, domain_to_dto_tag


def removeprefix(value: str, prefix: str) -> str:
    if value.startswith(prefix):
        return value[len(prefix) :]
    else:
        return value[:]


def domain_to_dto_download(download):
    location = removeprefix(download.location, "empire/server/downloads/")
    return Download(
        id=download.id,
        location=location,
        filename=download.filename,
        size=download.size,
        created_at=download.created_at,
        updated_at=download.updated_at,
        tags=list(map(lambda x: domain_to_dto_tag(x), download.tags)),
    )


class DownloadSourceFilter(str, Enum):
    upload = "upload"
    stager = "stager"
    agent_file = "agent_file"
    agent_task = "agent_task"


class DownloadOrderOptions(str, Enum):
    filename = "filename"
    location = "location"
    size = "size"
    created_at = "created_at"
    updated_at = "updated_at"


class Download(BaseModel):
    id: int
    location: str
    filename: str
    size: int
    created_at: datetime
    updated_at: datetime
    tags: List[Tag]


class Downloads(BaseModel):
    records: List[Download]
    limit: int
    page: int
    total_pages: int
    total: int
