from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, Query
from starlette.responses import FileResponse

from empire.server.api.api_router import APIRouter
from empire.server.api.jwt_auth import CurrentActiveUser, get_current_active_user
from empire.server.api.v2.download.download_dto import (
    Download,
    DownloadOrderOptions,
    Downloads,
    DownloadSourceFilter,
    domain_to_dto_download,
)
from empire.server.api.v2.shared_dependencies import (
    AppCtx,
    CurrentSession,
    SafeUploadFile,
    paginate,
)
from empire.server.api.v2.shared_dto import (
    BadRequestResponse,
    NotFoundResponse,
    OrderDirection,
)
from empire.server.api.v2.tag import tag_api
from empire.server.core.db import models
from empire.server.core.download_service import DownloadService


def get_download_service(main: AppCtx) -> DownloadService:
    return main.downloadsv2


DownloadServiceDep = Annotated[DownloadService, Depends(get_download_service)]


router = APIRouter(
    prefix="/api/v2/downloads",
    tags=["downloads"],
    responses={
        404: {"description": "Not found", "model": NotFoundResponse},
        400: {"description": "Bad request", "model": BadRequestResponse},
    },
    dependencies=[Depends(get_current_active_user)],
)


def get_download(
    uid: int,
    db: CurrentSession,
    download_service: DownloadServiceDep,
):
    download = download_service.get_by_id(db, uid)

    if download:
        return download

    raise HTTPException(404, f"Download not found for id {uid}")


DownloadDep = Annotated[models.Download, Depends(get_download)]


# Explicit types, so the served Content-Type does not depend on which mime
# database the host's distro ships. Starlette otherwise guesses via `mimetypes`,
# whose map varies by host and has no environment override.
_MEDIA_TYPES = {
    ".bat": "text/plain",
    ".cls": "text/plain",
    ".csv": "text/plain",
    ".hta": "text/plain",
    ".ino": "text/plain",
    ".log": "text/plain",
    ".ps1": "text/plain",
    ".py": "text/plain",
    ".sh": "text/plain",
    ".txt": "text/plain",
    ".vbs": "text/plain",
    ".xml": "text/plain",
    ".xsl": "text/plain",
    # Screenshots and avatars render inline in the UI. .svg is deliberately
    # absent: it is the one image type that carries script.
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def _media_type(filename: str) -> str:
    return _MEDIA_TYPES.get(Path(filename).suffix.lower(), "application/octet-stream")


@router.get("/{uid}/download", response_class=FileResponse)
def download_download(
    uid: int,
    db: CurrentSession,
    db_download: DownloadDep,
):
    filename = db_download.filename or db_download.location.split("/")[-1]

    return FileResponse(
        db_download.location, filename=filename, media_type=_media_type(filename)
    )


tag_api.add_endpoints_to_taggable(router, "/{uid}/tags", get_download)


@router.get(
    "/{uid}",
    response_model=Download,
)
def read_download(
    uid: int,
    db: CurrentSession,
    db_download: DownloadDep,
):
    return domain_to_dto_download(db_download)


@router.get("/", response_model=Downloads)
def read_downloads(
    db: CurrentSession,
    limit: int = -1,
    page: int = 1,
    order_direction: OrderDirection = OrderDirection.desc,
    order_by: DownloadOrderOptions = DownloadOrderOptions.updated_at,
    query: str | None = None,
    sources: list[DownloadSourceFilter] | None = Query(None),
    tags: list[str] | None = Query(None),
    *,
    download_service: DownloadServiceDep,
):
    downloads, total = download_service.get_all(
        db=db,
        download_types=sources,
        tags=tags,
        q=query,
        limit=limit,
        offset=(page - 1) * limit,
        order_by=order_by,
        order_direction=order_direction,
    )

    downloads_converted = [domain_to_dto_download(x) for x in downloads]

    page, total_pages = paginate(total, page, limit)
    return Downloads(
        records=downloads_converted,
        page=page,
        total_pages=total_pages,
        limit=limit,
        total=total,
    )


@router.post("/", status_code=201, response_model=Download)
def create_download(
    user: CurrentActiveUser,
    db: CurrentSession,
    download_service: DownloadServiceDep,
    file: SafeUploadFile,
):
    return domain_to_dto_download(download_service.create_download(db, user, file))
