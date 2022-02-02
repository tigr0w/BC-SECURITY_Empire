from datetime import datetime
from typing import List

from pydantic import BaseModel


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

