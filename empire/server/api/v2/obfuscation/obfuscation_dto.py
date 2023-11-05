from datetime import datetime

from pydantic import BaseModel, Field

from empire.server.core.db import models


class Keyword(BaseModel):
    id: int
    keyword: str
    replacement: str
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class Keywords(BaseModel):
    records: list[Keyword]


class KeywordUpdateRequest(BaseModel):
    keyword: str = Field(min_length=3)
    replacement: str = Field(min_length=3)


class KeywordPostRequest(BaseModel):
    keyword: str = Field(min_length=3)
    replacement: str = Field(min_length=3)


def domain_to_dto_obfuscation_config(obf_conf: models.ObfuscationConfig):
    return ObfuscationConfig(
        language=obf_conf.language,
        enabled=obf_conf.enabled,
        command=obf_conf.command,
        module=obf_conf.module,
        preobfuscatable=obf_conf.preobfuscatable,
    )


class ObfuscationConfig(BaseModel):
    language: str
    enabled: bool
    command: str
    module: str
    preobfuscatable: bool

    class Config:
        orm_mode = True


class ObfuscationConfigs(BaseModel):
    records: list[ObfuscationConfig]


class ObfuscationConfigUpdateRequest(BaseModel):
    enabled: bool
    command: str
    module: str
