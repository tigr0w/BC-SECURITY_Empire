import logging

from fastapi import Depends, HTTPException, Response
from sqlalchemy.orm import Session

from empire.server.api.api_router import APIRouter
from empire.server.api.jwt_auth import get_current_active_user
from empire.server.api.v2.module.module_dto import (
    Module,
    ModuleBulkUpdateRequest,
    ModuleScript,
    ModuleUpdateRequest,
    domain_to_dto_module,
)
from empire.server.api.v2.shared_dependencies import get_db
from empire.server.api.v2.shared_dto import BadRequestResponse, NotFoundResponse
from empire.server.core.module_models import EmpireModule
from empire.server.server import main

module_service = main.modulesv2

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v2/modules",
    tags=["modules"],
    responses={
        404: {"description": "Not found", "model": NotFoundResponse},
        400: {"description": "Bad request", "model": BadRequestResponse},
    },
    dependencies=[Depends(get_current_active_user)],
)


async def get_module(uid: str):
    module = module_service.get_by_id(uid)

    if module:
        return module

    raise HTTPException(status_code=404, detail=f"Module not found for id {uid}")


@router.get(
    "/",
    # todo is there an equivalent for this that doesn't cause fastapi to convert the object twice?
    #  Still want to display the response type in the docs
    # response_model=Modules,
)
async def read_modules():
    modules = list(
        map(
            lambda x: domain_to_dto_module(x[1], x[0]), module_service.get_all().items()
        )
    )

    return {"records": modules}


@router.get("/{uid}", response_model=Module)
async def read_module(uid: str, module: EmpireModule = Depends(get_module)):
    return domain_to_dto_module(module, uid)


@router.get("/{uid}/script", response_model=ModuleScript)
async def read_module_script(uid: str, module: EmpireModule = Depends(get_module)):
    script = module_service.get_module_script(module.id)

    if script:
        return ModuleScript(module_id=uid, script=script)

    raise HTTPException(status_code=404, detail=f"Module script not found for id {uid}")


@router.put("/{uid}", response_model=Module)
async def update_module(
    uid: str,
    module_req: ModuleUpdateRequest,
    module: EmpireModule = Depends(get_module),
    db: Session = Depends(get_db),
):
    module_service.update_module(db, module, module_req)

    return domain_to_dto_module(module, uid)


@router.put("/bulk/enable", status_code=204, response_class=Response)
async def update_bulk_enable(
    module_req: ModuleBulkUpdateRequest, db: Session = Depends(get_db)
):
    module_service.update_modules(db, module_req)


@router.post("/reload", status_code=204, response_class=Response)
async def reload_modules(
    db: Session = Depends(get_db),
):
    module_service.load_modules(db)


@router.post("/reset", status_code=204, response_class=Response)
async def reset_modules(
    db: Session = Depends(get_db),
):
    module_service.delete_all_modules(db)
    module_service.load_modules(db)
