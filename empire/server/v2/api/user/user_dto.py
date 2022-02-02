from datetime import datetime
from typing import List

from pydantic import BaseModel


# todo are notes personal?
#  should notes be expanded something that can be attached to any object and made private or public?
def domain_to_dto_user(user):
    return User(
        id=user.id,
        username=user.username,
        enabled=user.enabled,
        is_admin=user.admin,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


class User(BaseModel):
    id: int
    username: str
    enabled: bool
    is_admin: bool
    created_at: datetime
    updated_at: datetime


class Users(BaseModel):
    records: List[User]


class UserPostRequest(BaseModel):
    username: str
    password: str
    is_admin: bool


class UserUpdateRequest(BaseModel):
    username: str
    enabled: bool
    is_admin: bool


class UserUpdatePasswordRequest(BaseModel):
    password: str
