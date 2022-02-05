from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


def domain_to_dto_credential(credential):
    return Credential(
        id=credential.id,
        credtype=credential.credtype,
        domain=credential.domain,
        username=credential.username,
        password=credential.password,
        host=credential.host,
        os=credential.os,
        sid=credential.sid,
        notes=credential.notes,
        created_at=credential.created_at,
        updated_at=credential.updated_at,
    )


class Credential(BaseModel):
    id: int
    credtype: str  # todo enum?
    domain: str
    username: str
    password: str
    host: str
    os: Optional[str]
    sid: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


class Credentials(BaseModel):
    records: List[Credential]


class CredentialUpdateRequest(BaseModel):
    credtype: str  # todo enum?
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
    credtype: str  # todo enum?
    domain: str
    username: str
    password: str
    host: str
    os: Optional[str]
    sid: Optional[str]
    notes: Optional[str]
