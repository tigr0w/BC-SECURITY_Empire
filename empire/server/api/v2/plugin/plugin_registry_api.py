from fastapi import Depends, HTTPException

from empire.server.api.api_router import APIRouter
from empire.server.api.jwt_auth import (
    get_current_active_user,
)
from empire.server.api.v2.plugin.plugin_registry_dto import (
    MarketplaceResponse,
    PluginInstallRequest,
)
from empire.server.api.v2.shared_dependencies import CurrentSession
from empire.server.api.v2.shared_dto import BadRequestResponse, NotFoundResponse
from empire.server.core.exceptions import PluginValidationException
from empire.server.server import main

plugin_registry_service = main.pluginregistriesv2
plugin_service = main.pluginsv2

router = APIRouter(
    prefix="/api/v2/plugin-registries",
    tags=["plugins"],
    responses={
        404: {"description": "Not found", "model": NotFoundResponse},
        400: {"description": "Bad request", "model": BadRequestResponse},
    },
    dependencies=[Depends(get_current_active_user)],
)


@router.get("/marketplace", response_model=MarketplaceResponse)
async def get_marketplace(db: CurrentSession):
    return MarketplaceResponse.model_validate(
        plugin_registry_service.get_marketplace(db)
    )


@router.post("/marketplace/install")
async def install_plugin(install_req: PluginInstallRequest, db: CurrentSession):
    try:
        plugin_registry_service.install_plugin(
            db, install_req.name, install_req.version, install_req.registry
        )
    except PluginValidationException as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
