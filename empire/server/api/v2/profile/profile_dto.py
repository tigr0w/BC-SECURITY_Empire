from datetime import datetime

from pydantic import BaseModel


class Profile(BaseModel):
    id: int
    name: str
    file_path: str | None  # todo vr needed?
    category: str
    data: str
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class Profiles(BaseModel):
    records: list[Profile]


# name can't be modified atm because of the way name is inferred from the file name.
# could be fixed later on.
class ProfileUpdateRequest(BaseModel):
    data: str


class ProfilePostRequest(BaseModel):
    name: str
    category: str
    data: str
