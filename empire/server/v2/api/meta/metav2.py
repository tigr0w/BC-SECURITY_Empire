from fastapi import HTTPException, Depends

import empire.server.common.empire
from empire.server.server import main
from empire.server.v2.api.EmpireApiRouter import APIRouter
from empire.server.v2.api.jwt_auth import get_current_active_user
from empire.server.v2.api.meta.meta_dto import EmpireVersion

listener_service = main.listenersv2

router = APIRouter(
    prefix="/api/v2beta/meta",
    tags=["meta"],
    responses={404: {"description": "Not found"}},
)


@router.get("/version", response_model=EmpireVersion, dependencies=[Depends(get_current_active_user)])
async def read_empire_version():
    return {"version": empire.server.common.empire.VERSION.split(" ")[0]}
