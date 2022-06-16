from fastapi import Depends, HTTPException

from empire.server.server import main
from empire.server.v2.api.EmpireApiRouter import APIRouter
from empire.server.v2.api.jwt_auth import get_current_active_user
from empire.server.v2.api.shared_dto import BadRequestResponse, NotFoundResponse
from empire.server.v2.api.stager.stager_dto import (
    StagerTemplate,
    StagerTemplates,
    domain_to_dto_template,
)

stager_template_service = main.stagertemplatesv2

router = APIRouter(
    prefix="/api/v2beta/stager-templates",
    tags=["stager-templates"],
    responses={
        404: {"description": "Not found", "model": NotFoundResponse},
        400: {"description": "Bad request", "model": BadRequestResponse},
    },
    dependencies=[Depends(get_current_active_user)],
)


@router.get("/", response_model=StagerTemplates)
async def get_stager_templates():
    templates = list(
        map(
            lambda x: domain_to_dto_template(x[1], x[0]),
            stager_template_service.get_stager_templates(),
        )
    )

    return {"records": templates}


@router.get(
    "/{uid}",
    response_model=StagerTemplate,
)
async def get_stager_template(uid: str):
    template = stager_template_service.get_stager_template(uid)

    if not template:
        raise HTTPException(status_code=404, detail="Stager template not found")

    return domain_to_dto_template(template, uid)
