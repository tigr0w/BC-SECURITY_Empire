from fastapi import HTTPException, Depends, File, UploadFile
from sqlalchemy.orm import Session
from starlette.responses import FileResponse

from empire.server.database import models
from empire.server.server import main
from empire.server.v2.api.EmpireApiRouter import APIRouter
from empire.server.v2.api.jwt_auth import get_current_active_user
from empire.server.v2.api.shared_dependencies import get_db

download_service = main.downloadsv2

router = APIRouter(
    prefix="/api/v2beta/downloads",
    tags=["downloads"],
    responses={404: {"description": "Not found"}},
)


async def get_download(uid: int, db: Session = Depends(get_db)):
    download = download_service.get_by_id(db, uid)

    if download:
        return download

    raise HTTPException(404, f'Download not found for id {uid}')


@router.get("/{uid}", response_class=FileResponse, dependencies=[Depends(get_current_active_user)])
async def read_download(uid: int,
                        db: Session = Depends(get_db),
                        db_download: models.Download = Depends(get_download)):
    if db_download.filename:
        filename = db_download.filename
    else:
        filename = db_download.location.split('/')[-1]

    return FileResponse(db_download.location, filename=filename)


# todo At the moment downloads don't have a backref to their joined objects.
#  maybe that's fine?
# todo remove the install path from the location?
# todo { records: [] }
@router.get("/", dependencies=[Depends(get_current_active_user)])
async def read_downloads(db: Session = Depends(get_db),
                         query: str = None):
    return download_service.get_all(db, query)


@router.post("/", dependencies=[Depends(get_current_active_user)])
async def create_download(db: Session = Depends(get_db),
                          file: UploadFile = File(...)):
    return download_service.create_download(db, file)
