import typing
from enum import Enum
from typing import List

from pydantic import BaseModel

from empire.server.database import models


class ValueType(str, Enum):
    string = "STRING"
    float = "FLOAT"
    integer = "INTEGER"
    boolean = "BOOLEAN"


class CustomOptionSchema(BaseModel):
    description: str
    required: bool
    value: str
    suggested_values: List[str]
    strict: bool
    value_type: ValueType


class OrderDirection(str, Enum):
    asc = "asc"
    desc = "desc"


class DownloadDescription(BaseModel):
    id: int
    file_name: str
    link: str

    class Config:
        orm_mode = True


def domain_to_dto_download_description(download: models.Download):
    if download.filename:  # todo can this be made as a @property?
        filename = download.filename
    else:
        filename = download.location.split('/')[-1]

    return DownloadDescription(
        id=download.id,
        file_name=filename,
        link=f'/api/v2beta/downloads/{download.id}'
    )


def to_value_type(value: typing.Any) -> ValueType:
    if isinstance(value, str):
        return ValueType.string
    elif isinstance(value, bool):
        return ValueType.boolean
    elif isinstance(value, float):
        return ValueType.float
    elif isinstance(value, int):
        return ValueType.integer
    else:
        return ValueType.string
