from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from empire.server.api.v2.tag.tag_dto import Tag, domain_to_dto_tag


def domain_to_dto_credential(credential):
    return Credential(
        id=credential.id,
        credtype=credential.credtype,
        domain=credential.domain,
        username=credential.username,
        password=credential.password,
        host=credential.host,  # for now, host is not joined.
        os=credential.os,
        sid=credential.sid,
        notes=credential.notes,
        created_at=credential.created_at,
        updated_at=credential.updated_at,
        tags=list(map(lambda x: domain_to_dto_tag(x), credential.tags)),
    )


class Credential(BaseModel):
    id: int
    credtype: str
    domain: str
    username: str
    password: str
    host: str
    os: Optional[str]
    sid: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    tags: List[Tag]


class Credentials(BaseModel):
    records: List[Credential]


class CredentialUpdateRequest(BaseModel):
    credtype: str
    domain: str
    username: str
    password: str
    host: str
    os: str
    sid: str
    notes: str
    os: Optional[str]
    sid: Optional[str]
    notes: Optional[str]


class CredentialPostRequest(BaseModel):
    credtype: str
    domain: str
    username: str
    password: str
    host: str
    os: Optional[str]
    sid: Optional[str]
    notes: Optional[str]
