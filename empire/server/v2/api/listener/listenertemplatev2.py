from fastapi import Depends, HTTPException

from empire.server.server import main
from empire.server.v2.api.EmpireApiRouter import APIRouter
from empire.server.v2.api.jwt_auth import get_current_active_user
from empire.server.v2.api.listener.listener_dto import (
    ListenerTemplate,
    ListenerTemplates,
    domain_to_dto_template,
)
from empire.server.v2.api.shared_dto import BadRequestResponse, NotFoundResponse

listener_template_service = main.listenertemplatesv2

router = APIRouter(
    prefix="/api/v2beta/listener-templates",
    tags=["listener-templates"],
    responses={
        404: {"description": "Not found", "model": NotFoundResponse},
        400: {"description": "Bad request", "model": BadRequestResponse},
    },
    dependencies=[Depends(get_current_active_user)],
)


@router.get(
    "/",
    response_model=ListenerTemplates,
)
async def get_listener_templates():
    templates = list(
        map(
            lambda x: domain_to_dto_template(x[1], x[0]),
            listener_template_service.get_listener_templates(),
        )
    )

    return {"records": templates}


@router.get(
    "/{uid}",
    response_model=ListenerTemplate,
)
async def get_listener_template(uid: str):
    template = listener_template_service.get_listener_template(uid)

    if not template:
        raise HTTPException(status_code=404, detail="Listener template not found")

    return domain_to_dto_template(template, uid)
