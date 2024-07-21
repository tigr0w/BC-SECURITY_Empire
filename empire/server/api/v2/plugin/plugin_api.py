from fastapi import Depends, HTTPException
from starlette.responses import Response

from empire.server.api.api_router import APIRouter
from empire.server.api.jwt_auth import (
    CurrentUser,
    get_current_active_user,
)
from empire.server.api.v2.plugin.plugin_dto import (
    PluginExecutePostRequest,
    PluginExecuteResponse,
    Plugins,
    PluginUpdateRequest,
    domain_to_dto_plugin,
)
from empire.server.api.v2.shared_dependencies import CurrentSession
from empire.server.api.v2.shared_dto import BadRequestResponse, NotFoundResponse
from empire.server.core.exceptions import (
    PluginExecutionException,
    PluginValidationException,
)
from empire.server.core.plugins import BasePlugin
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


async def get_plugin(uid: str) -> BasePlugin:
    plugin = plugin_service.get_by_id(uid)

    if plugin:
        return plugin

    raise HTTPException(status_code=404, detail=f"Plugin not found for id {uid}")


@router.get("/", response_model=Plugins)
async def read_plugins(db: CurrentSession):
    plugins = [domain_to_dto_plugin(x[1], db) for x in plugin_service.get_all().items()]

    return {"records": plugins}


@router.get("/{uid}")
async def read_plugin(uid: str, db: CurrentSession, plugin=Depends(get_plugin)):
    return domain_to_dto_plugin(plugin, db)


@router.post("/{uid}/execute", response_model=PluginExecuteResponse)
async def execute_plugin(
    uid: str,
    plugin_req: PluginExecutePostRequest,
    db: CurrentSession,
    current_user: CurrentUser,
    plugin=Depends(get_plugin),
):
    try:
        results, err = plugin_service.execute_plugin(
            db, plugin, plugin_req, current_user
        )
    except PluginValidationException as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except PluginExecutionException as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    if results is False or err:
        raise HTTPException(500, err or "internal plugin error")

    if results in [True, None]:
        return {"detail": "Plugin executed successfully"}

    return {"detail": results}


@router.put("/{uid}", status_code=200)
async def update_plugin(
    uid: str,
    plugin_update_req: PluginUpdateRequest,
    db: CurrentSession,
    plugin=Depends(get_plugin),
):
    plugin_service.update_plugin_enabled(db, plugin, plugin_update_req.enabled)
    return domain_to_dto_plugin(plugin, db)


@router.post("/reload", status_code=204, response_class=Response)
async def reload_plugins(db: CurrentSession):
    plugin_service.shutdown()
    plugin_service.load_plugins(db)
