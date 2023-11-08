from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from empire.server.core.db.base import SessionLocal


def get_db():
    with SessionLocal.begin() as db:
        yield db


CurrentSession = Annotated[Session, Depends(get_db)]
