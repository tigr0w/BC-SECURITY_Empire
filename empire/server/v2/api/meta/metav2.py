from fastapi import Depends, HTTPException

import empire.server.common.empire
from empire.server.server import main
from empire.server.v2.api.EmpireApiRouter import APIRouter
from empire.server.v2.api.jwt_auth import get_current_active_user
from empire.server.v2.api.meta.meta_dto import EmpireVersion
from empire.server.v2.api.shared_dto import BadRequestResponse, NotFoundResponse

listener_service = main.listenersv2

router = APIRouter(
    prefix="/api/v2beta/meta",
    tags=["meta"],
    responses={
        404: {"description": "Not found", "model": NotFoundResponse},
        400: {"description": "Bad request", "model": BadRequestResponse},
    },
    dependencies=[Depends(get_current_active_user)],
)


@router.get(
    "/version",
    response_model=EmpireVersion,
)
async def read_empire_version():
    return {"version": empire.server.common.empire.VERSION.split(" ")[0]}
