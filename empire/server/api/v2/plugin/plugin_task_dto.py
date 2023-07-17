from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel

from empire.server.api.v2.shared_dto import (
    DownloadDescription,
    domain_to_dto_download_description,
)
from empire.server.api.v2.tag.tag_dto import Tag, domain_to_dto_tag
from empire.server.core.db import models


class PluginTaskOrderOptions(str, Enum):
    id = "id"
    updated_at = "updated_at"
    status = "status"
    plugin = "plugin"


def domain_to_dto_plugin_task(
    task: models.PluginTask,
    include_full_input: bool = True,
    include_output: bool = True,
):
    return PluginTask.construct(  # .construct doesn't do any validation and speeds up the request a bit
        id=task.id,
        input=task.input,
        full_input=None if not include_full_input else task.input_full,
        output=None if not include_output else task.output,
        user_id=task.user_id,
        username=None if not task.user else task.user.username,
        plugin_id=task.plugin_id,
        downloads=list(
            map(lambda x: domain_to_dto_download_description(x), task.downloads)
        ),
        status=task.status,
        created_at=task.created_at,
        updated_at=task.updated_at,
        tags=list(map(lambda x: domain_to_dto_tag(x), task.tags)),
    )


class PluginTask(BaseModel):
    id: int
    input: str
    full_input: Optional[str]
    output: Optional[str]
    user_id: Optional[int]
    username: Optional[str]
    plugin_id: str
    downloads: List[DownloadDescription]
    status: Optional[models.PluginTaskStatus]
    created_at: datetime
    updated_at: datetime
    tags: List[Tag]


class PluginTasks(BaseModel):
    records: List[PluginTask]
    limit: int
    page: int
    total_pages: int
    total: int
