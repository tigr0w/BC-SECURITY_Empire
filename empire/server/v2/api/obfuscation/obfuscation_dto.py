from datetime import datetime
from typing import List

from pydantic import BaseModel

from empire.server.database import models


class Keyword(BaseModel):
    id: int
    keyword: str
    replacement: str
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class Keywords(BaseModel):
    records: List[Keyword]


class KeywordUpdateRequest(BaseModel):
    keyword: str
    replacement: str


class KeywordPostRequest(BaseModel):
    keyword: str
    replacement: str


def domain_to_dto_obfuscation_config(obf_conf: models.ObfuscationConfig):
    return ObfuscationConfig(
        language=obf_conf.language,
        enabled=obf_conf.enabled,
        command=obf_conf.command,
        module=obf_conf.module,
    )


class ObfuscationConfig(BaseModel):
    language: str
    enabled: bool
    command: str
    module: str


class ObfuscationConfigUpdateRequest(BaseModel):
    enabled: bool
    command: str
    module: str
