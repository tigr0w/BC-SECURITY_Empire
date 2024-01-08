from fastapi import Depends

from empire.server.api.api_router import APIRouter
from empire.server.api.jwt_auth import get_current_active_admin_user
from empire.server.api.v2.shared_dependencies import CurrentSession
from empire.server.api.v2.shared_dto import BadRequestResponse, NotFoundResponse
from empire.server.server import main

ip_service = main.ipsv2

router = APIRouter(
    prefix="/api/v2/admin",
    tags=["admin"],
    responses={
        404: {"description": "Not found", "model": NotFoundResponse},
        400: {"description": "Bad request", "model": BadRequestResponse},
    },
    dependencies=[Depends(get_current_active_admin_user)],
)


@router.put("/ip_filtering")
async def toggle_ip_filtering(db: CurrentSession, enabled: bool):
    ip_service.toggle_ip_filtering(db, enabled)
