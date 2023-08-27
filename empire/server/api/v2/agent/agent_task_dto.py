from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field

from empire.server.api.v2.shared_dto import (
    DownloadDescription,
    domain_to_dto_download_description,
)
from empire.server.api.v2.tag.tag_dto import Tag, domain_to_dto_tag
from empire.server.core.db import models


class AgentTaskOrderOptions(str, Enum):
    id = "id"
    updated_at = "updated_at"
    status = "status"
    agent = "agent"


def domain_to_dto_task(
    task: models.AgentTask,
    include_full_input: bool = True,
    include_original_output: bool = True,
    include_output: bool = True,
):
    return AgentTask.construct(  # .construct doesn't do any validation and speeds up the request a bit
        id=task.id,
        input=task.input,
        full_input=None if not include_full_input else task.input_full,
        output=None if not include_output else task.output,
        original_output=None if not include_original_output else task.original_output,
        user_id=task.user_id,
        username=None if not task.user else task.user.username,
        agent_id=task.agent_id,
        downloads=list(
            map(lambda x: domain_to_dto_download_description(x), task.downloads)
        ),
        module_name=task.module_name,
        task_name=task.task_name,
        status=task.status,
        created_at=task.created_at,
        updated_at=task.updated_at,
        tags=list(map(lambda x: domain_to_dto_tag(x), task.tags)),
    )


class AgentTask(BaseModel):
    id: int
    input: str
    full_input: Optional[str]
    output: Optional[str]
    original_output: Optional[str]
    user_id: Optional[int]
    username: Optional[str]
    agent_id: str
    downloads: List[DownloadDescription]
    module_name: Optional[str]
    task_name: Optional[str]
    status: models.AgentTaskStatus
    created_at: datetime
    updated_at: datetime
    tags: List[Tag]


class AgentTasks(BaseModel):
    records: List[AgentTask]
    limit: int
    page: int
    total_pages: int
    total: int


class ShellPostRequest(BaseModel):
    command: str
    literal: bool = False


class ModulePostRequest(BaseModel):
    module_id: str
    ignore_language_version_check: bool = False
    ignore_admin_check: bool = False
    options: Dict[str, Union[str, int, float]]
    modified_input: Optional[str] = None


class DownloadPostRequest(BaseModel):
    path_to_file: str


class UploadPostRequest(BaseModel):
    path_to_file: str
    file_id: int


class ScriptCommandPostRequest(BaseModel):
    command: str


class SysinfoPostRequest(BaseModel):
    pass


class SleepPostRequest(BaseModel):
    delay: int = Field(ge=0)
    jitter: float = Field(ge=0, le=1)


class CommsPostRequest(BaseModel):
    new_listener_id: int


class KillDatePostRequest(BaseModel):
    kill_date: str  # todo validator. Or can we just set it to a datetime. same with killdate on the agent dto


class WorkingHoursPostRequest(BaseModel):
    working_hours: str  # todo validator.


class DirectoryListPostRequest(BaseModel):
    path: str


class ProxyEnum(str, Enum):
    socks4 = "SOCKS4"
    socks5 = "SOCKS5"
    http = "HTTP"
    ssl = "SSL"
    ssl_weak = "SSL_WEAK"
    ssl_anon = "SSL_ANON"
    tor = "TOR"
    https = "HTTPS"
    http_connect = "HTTP_CONNECT"
    https_connect = "HTTPS_CONNECT"


class ProxyItem(BaseModel):
    proxy_type: ProxyEnum
    host: str
    port: int


class ProxyListPostRequest(BaseModel):
    proxies: List[ProxyItem]


class ExitPostRequest(BaseModel):
    pass


class SocksPostRequest(BaseModel):
    port: int


class KillJobPostRequest(BaseModel):
    id: int
