from fastapi import Depends, HTTPException

from empire.server.server import main
from empire.server.v2.api.EmpireApiRouter import APIRouter
from empire.server.v2.api.jwt_auth import get_current_active_user
from empire.server.v2.api.listener.listener_dto import (
    ListenerTemplate,
    ListenerTemplates,
    domain_to_dto_template,
)

listener_template_service = main.listenertemplatesv2

router = APIRouter(
    prefix="/api/v2beta/listener-templates",
    tags=["listener-templates"],
    responses={404: {"description": "Not found"}},
)


@router.get(
    "/",
    response_model=ListenerTemplates,
    dependencies=[Depends(get_current_active_user)],
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
    dependencies=[Depends(get_current_active_user)],
)
async def get_listener_template(uid: str):
    template = listener_template_service.get_listener_template(uid)

    if not template:
        raise HTTPException(status_code=404, detail="Listener template not found")

    return domain_to_dto_template(template, uid)
