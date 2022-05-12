from datetime import datetime
from typing import List

from pydantic import BaseModel


# TODO VR Authors
def domain_to_dto_bypass(bypass):
    return Bypass(
        id=bypass.id,
        name=bypass.name,
        code=bypass.code,
        created_at=bypass.created_at,
        updated_at=bypass.updated_at,
    )


class Bypass(BaseModel):
    id: int
    name: str
    code: str
    created_at: datetime
    updated_at: datetime


class Bypasses(BaseModel):
    records: List[Bypass]


class BypassUpdateRequest(BaseModel):
    name: str
    code: str


class BypassPostRequest(BaseModel):
    name: str
    code: str
