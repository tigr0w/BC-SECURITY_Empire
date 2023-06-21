from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from starlette.responses import Response

from empire.server.api.api_router import APIRouter
from empire.server.api.jwt_auth import get_current_active_user, get_current_user
from empire.server.api.v2.plugin.plugin_dto import (
    PluginExecutePostRequest,
    PluginExecuteResponse,
    Plugins,
    domain_to_dto_plugin,
)
from empire.server.api.v2.shared_dependencies import get_db
from empire.server.api.v2.shared_dto import BadRequestResponse, NotFoundResponse
from empire.server.core.db import models
from empire.server.server import main

plugin_service = main.pluginsv2

router = APIRouter(
    prefix="/api/v2/plugins",
    tags=["plugins"],
    responses={
        404: {"description": "Not found", "model": NotFoundResponse},
        400: {"description": "Bad request", "model": BadRequestResponse},
    },
    dependencies=[Depends(get_current_active_user)],
)


async def get_plugin(uid: str):
    plugin = plugin_service.get_by_id(uid)

    if plugin:
        return plugin

    raise HTTPException(status_code=404, detail=f"Plugin not found for id {uid}")


@router.get("/", response_model=Plugins)
async def read_plugins():
    plugins = list(
        map(
            lambda x: domain_to_dto_plugin(x[1], x[0]), plugin_service.get_all().items()
        )
    )

    return {"records": plugins}


@router.get("/{uid}")
async def read_plugin(uid: str, plugin=Depends(get_plugin)):
    return domain_to_dto_plugin(plugin, uid)


@router.post("/{uid}/execute", response_model=PluginExecuteResponse)
async def execute_plugin(
    uid: str,
    plugin_req: PluginExecutePostRequest,
    plugin=Depends(get_plugin),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    results, err = plugin_service.execute_plugin(db, plugin, plugin_req, current_user)

    # A plugin can return False for some internal error,
    #  or it can raise an actual exception.
    if results is False:
        raise HTTPException(500, "internal plugin error")
    if err:
        raise HTTPException(status_code=400, detail=err)
    return {} if results is None else {"detail": results}


@router.post("/reload", status_code=204, response_class=Response)
async def reload_plugins(db: Session = Depends(get_db)):
    plugin_service.shutdown()
    plugin_service.startup_plugins(db)
