from typing import Annotated

from fastapi import Depends, HTTPException

from empire.server.api.api_router import APIRouter
from empire.server.api.jwt_auth import get_current_active_user
from empire.server.api.v2.shared_dependencies import AppCtx, CurrentSession
from empire.server.api.v2.shared_dto import BadRequestResponse, NotFoundResponse
from empire.server.api.v2.stager.stager_dto import (
    StagerTemplate,
    StagerTemplates,
    domain_to_dto_template,
)
from empire.server.core.stager_template_service import StagerTemplateService
from empire.server.utils.option_util import get_listener_defaults


def get_stager_template_service(main: AppCtx) -> StagerTemplateService:
    return main.stagertemplatesv2


StagerTemplateServiceDep = Annotated[
    StagerTemplateService, Depends(get_stager_template_service)
]


router = APIRouter(
    prefix="/api/v2/stager-templates",
    tags=["stager-templates"],
    responses={
        404: {"description": "Not found", "model": NotFoundResponse},
        400: {"description": "Bad request", "model": BadRequestResponse},
    },
    dependencies=[Depends(get_current_active_user)],
)


@router.get("/", response_model=StagerTemplates)
def get_stager_templates(
    db: CurrentSession,
    stager_template_service: StagerTemplateServiceDep,
):
    default_listener, listener_names = get_listener_defaults(db)
    templates = [
        domain_to_dto_template(x[1], x[0], default_listener, listener_names)
        for x in stager_template_service.get_stager_templates().items()
    ]

    return {"records": templates}


@router.get(
    "/{uid}",
    response_model=StagerTemplate,
)
def get_stager_template(
    uid: str,
    db: CurrentSession,
    stager_template_service: StagerTemplateServiceDep,
):
    template = stager_template_service.get_stager_template(uid)

    if not template:
        raise HTTPException(status_code=404, detail="Stager template not found")

    default_listener, listener_names = get_listener_defaults(db)
    return domain_to_dto_template(template, uid, default_listener, listener_names)
