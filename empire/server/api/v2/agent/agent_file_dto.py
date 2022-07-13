# needed for self referencing
# https://pydantic-docs.helpmanual.io/usage/postponed_annotations/#self-referencing-models
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel

from empire.server.api.v2.shared_dto import (
    DownloadDescription,
    domain_to_dto_download_description,
)
from empire.server.database import models


def domain_to_dto_file(file: models.AgentFile, children: List[models.AgentFile]):
    return AgentFile(
        id=file.id,
        session_id=file.session_id,
        name=file.name,
        path=file.path,
        is_file=file.is_file,
        parent_id=file.parent_id,
        downloads=list(
            map(lambda x: domain_to_dto_download_description(x), file.downloads)
        ),
        children=list(map(lambda c: domain_to_dto_file(c, []), children)),
    )


class AgentFile(BaseModel):
    id: int
    session_id: str
    name: str
    path: str
    is_file: bool
    parent_id: Optional[int]
    downloads: List[DownloadDescription]
    children: List[AgentFile] = []

    class Config:
        orm_mode = True


AgentFile.update_forward_refs()
