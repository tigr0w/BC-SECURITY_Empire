from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from empire.server.server import main
from empire.server.v2.api.EmpireApiRouter import APIRouter
from empire.server.v2.api.jwt_auth import get_current_active_user
from empire.server.v2.api.plugin.plugin_dto import (
    PluginExecutePostRequest,
    domain_to_dto_plugin,
)
from empire.server.v2.api.shared_dependencies import get_db

plugin_service = main.pluginsv2

router = APIRouter(
    prefix="/api/v2beta/plugins",
    tags=["plugins"],
    responses={404: {"description": "Not found"}},
)


async def get_plugin(uid: str):
    plugin = plugin_service.get_by_id(uid)

    if plugin:
        return plugin

    raise HTTPException(status_code=404, detail=f"Plugin not found for id {uid}")


@router.get(
    "/",
    # todo is there an equivalent for this that doesn't cause fastapi to convert the object twice?
    #  Still want to display the response type in the docs
    # response_model=Modules,
    dependencies=[Depends(get_current_active_user)],
)
async def read_plugins():
    plugins = list(
        map(
            lambda x: domain_to_dto_plugin(x[1], x[0]), plugin_service.get_all().items()
        )
    )

    return {"records": plugins}


@router.get("/{uid}", dependencies=[Depends(get_current_active_user)])
async def read_plugin(uid: str, plugin=Depends(get_plugin)):
    return domain_to_dto_plugin(plugin, uid)


@router.post("/{uid}/execute", dependencies=[Depends(get_current_active_user)])
async def execute_module(
    uid: str,
    plugin_req: PluginExecutePostRequest,
    plugin=Depends(get_plugin),
    db: Session = Depends(get_db),
):
    # todo can this logic be moved to the service
    #  and can the field parsing be abstracted out with the others?
    #  Since this modifies shared object state, probably need a lock on each plugin.
    # set all passed module options
    for key, value in plugin_req.options.items():
        if key not in plugin.options:
            raise HTTPException(400, f"invalid module option {key}")

        plugin.options[key]["Value"] = value

    for option, values in plugin.options.items():
        if values["Required"] and ((not values["Value"]) or (values["Value"] == "")):
            raise HTTPException(400, f"required module option missing {option}")
        if values["Strict"] and values["Value"] not in values["SuggestedValues"]:
            raise HTTPException(
                400, f"{option} must be set to one of suggested values."
            )

    results = plugin.execute(plugin_req.options)
    if results is False:
        raise HTTPException(500, "internal plugin error")
    return {} if results is None else results
