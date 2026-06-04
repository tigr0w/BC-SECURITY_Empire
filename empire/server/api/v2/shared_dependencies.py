import math
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from empire.server.common.empire import MainMenu
from empire.server.core.db.base import SessionLocal


def get_db():
    with SessionLocal.begin() as db:
        yield db


def get_main() -> MainMenu:
    from empire.server.server import main

    return main


def paginate(total: int, page: int, limit: int) -> tuple[int, int]:
    """Compute (page, total_pages) for a paginated response.

    A non-positive `limit` (the project's `-1` "unbounded" sentinel, or `0`)
    collapses the response to a single page: `page` is normalized to `1`, and
    `total_pages` is `1` when any rows exist and `0` otherwise.
    """
    if limit <= 0:
        return 1, 1 if total > 0 else 0
    return page, math.ceil(total / limit)


CurrentSession = Annotated[Session, Depends(get_db)]
AppCtx = Annotated[MainMenu, Depends(get_main)]
