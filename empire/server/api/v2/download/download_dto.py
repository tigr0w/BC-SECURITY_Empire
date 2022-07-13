from datetime import datetime
from enum import Enum
from typing import List

from pydantic import BaseModel


def domain_to_dto_download(download):
    return Download(
        id=download.id,
        location=download.location,
        filename=download.filename,
        size=download.size,
        created_at=download.created_at,
        updated_at=download.updated_at,
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


class Downloads(BaseModel):
    records: List[Download]
    limit: int
    page: int
    total_pages: int
    total: int
