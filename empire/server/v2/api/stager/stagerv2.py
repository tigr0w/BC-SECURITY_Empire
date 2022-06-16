from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from starlette.responses import Response
from starlette.status import HTTP_204_NO_CONTENT

from empire.server.database import models
from empire.server.server import main
from empire.server.v2.api.EmpireApiRouter import APIRouter
from empire.server.v2.api.jwt_auth import get_current_active_user
from empire.server.v2.api.shared_dependencies import get_db
from empire.server.v2.api.shared_dto import BadRequestResponse, NotFoundResponse
from empire.server.v2.api.stager.stager_dto import (
    Stager,
    StagerPostRequest,
    Stagers,
    StagerUpdateRequest,
    domain_to_dto_stager,
)

stager_service = main.stagersv2

router = APIRouter(
    prefix="/api/v2beta/stagers",
    tags=["stagers"],
    responses={
        404: {"description": "Not found", "model": NotFoundResponse},
        400: {"description": "Bad request", "model": BadRequestResponse},
    },
    dependencies=[Depends(get_current_active_user)],
)


async def get_stager(uid: int, db: Session = Depends(get_db)):
    stager = stager_service.get_by_id(db, uid)

    if stager:
        return stager

    raise HTTPException(404, f"Stager not found for id {uid}")


@router.get("/", response_model=Stagers)
async def read_stagers(db: Session = Depends(get_db)):
    stagers = list(map(lambda x: domain_to_dto_stager(x), stager_service.get_all(db)))

    return {"records": stagers}


@router.get("/{uid}", response_model=Stager)
async def read_stager(uid: int, db_stager: models.Stager = Depends(get_stager)):
    return domain_to_dto_stager(db_stager)


@router.post("/", status_code=201, response_model=Stager)
async def create_stager(
    stager_req: StagerPostRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
    save: bool = True,
):
    resp, err = stager_service.create_stager(
        db, stager_req, save, user_id=current_user.id
    )

    if err:
        raise HTTPException(status_code=400, detail=err)

    return domain_to_dto_stager(resp)


@router.put("/{uid}", response_model=Stager)
async def update_stager(
    uid: int,
    stager_req: StagerUpdateRequest,
    db: Session = Depends(get_db),
    db_stager: models.Stager = Depends(get_stager),
):
    resp, err = stager_service.update_stager(db, db_stager, stager_req)

    if err:
        raise HTTPException(status_code=400, detail=err)

    return domain_to_dto_stager(resp)


@router.delete(
    "/{uid}",
    status_code=HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_stager(
    uid: int,
    db: Session = Depends(get_db),
    db_stager: models.Stager = Depends(get_stager),
):
    stager_service.delete_stager(db, db_stager)
