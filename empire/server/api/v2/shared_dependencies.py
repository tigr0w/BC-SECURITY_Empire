import math
from typing import Annotated

from fastapi import Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session
from starlette import status

from empire.server.common.empire import MainMenu
from empire.server.core.db.base import SessionLocal
from empire.server.utils.file_util import safe_filename


def get_db():
    with SessionLocal.begin() as db:
        yield db


def get_main(request: Request) -> MainMenu:
    # We use app state here because we have a lot of long-lived singletons
    # that can't be request scoped. create_app() initializes main to None and
    # the lifespan populates it on startup, so a None here means a request
    # arrived before startup finished — keep the None check so it 503s cleanly
    # instead of handing out an uninitialized context.
    main = request.app.state.main
    if main is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Empire application context is not initialized yet.",
        )
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


def validate_upload(file: UploadFile = File(...)) -> UploadFile:
    """Reject an uploaded file whose name is a path-traversal attempt.

    Boundary guard for every upload endpoint; the download service enforces the
    same rule again at the point it builds the destination path.
    """
    if safe_filename(file.filename) is None:
        raise HTTPException(status_code=400, detail="Invalid filename.")
    return file


CurrentSession = Annotated[Session, Depends(get_db)]
AppCtx = Annotated[MainMenu, Depends(get_main)]
SafeUploadFile = Annotated[UploadFile, Depends(validate_upload)]
