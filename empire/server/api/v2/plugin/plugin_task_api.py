import math
from datetime import datetime
from typing import List, Optional

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from empire.server.api.api_router import APIRouter
from empire.server.api.jwt_auth import get_current_active_user
from empire.server.api.v2.plugin.plugin_task_dto import (
    PluginTask,
    PluginTaskOrderOptions,
    PluginTasks,
    domain_to_dto_plugin_task,
)
from empire.server.api.v2.shared_dependencies import get_db
from empire.server.api.v2.shared_dto import (
    BadRequestResponse,
    NotFoundResponse,
    OrderDirection,
)
from empire.server.api.v2.tag import tag_api
from empire.server.api.v2.tag.tag_dto import TagStr
from empire.server.core.db import models
from empire.server.core.db.models import PluginTaskStatus
from empire.server.core.download_service import DownloadService
from empire.server.core.plugin_service import PluginService
from empire.server.server import main

download_service: DownloadService = main.downloadsv2
plugin_service: PluginService = main.pluginsv2

router = APIRouter(
    prefix="/api/v2/plugins",
    tags=["plugins", "tasks"],
    responses={
        404: {"description": "Not found", "model": NotFoundResponse},
        400: {"description": "Bad request", "model": BadRequestResponse},
    },
    dependencies=[Depends(get_current_active_user)],
)


async def get_plugin(plugin_id: str):
    plugin = plugin_service.get_by_id(plugin_id)

    if plugin:
        return plugin

    raise HTTPException(404, f"Plugin not found for id {plugin_id}")


async def get_task(uid: int, db: Session = Depends(get_db), plugin=Depends(get_plugin)):
    task = plugin_service.get_task(db, plugin.info["Name"], uid)

    if task:
        return task

    raise HTTPException(
        404, f"Task not found for plugin {plugin.info['Name']} and task id {uid}"
    )


tag_api.add_endpoints_to_taggable(router, "/{plugin_id}/tasks/{uid}/tags", get_task)


@router.get("/tasks", response_model=PluginTasks)
async def read_tasks_all_plugins(
    limit: int = -1,
    page: int = 1,
    include_full_input: bool = False,
    include_output: bool = True,
    since: Optional[datetime] = None,
    order_by: PluginTaskOrderOptions = PluginTaskOrderOptions.id,
    order_direction: OrderDirection = OrderDirection.desc,
    status: Optional[PluginTaskStatus] = None,
    plugins: Optional[List[str]] = Query(None),
    users: Optional[List[int]] = Query(None),
    tags: Optional[List[TagStr]] = Query(None),
    query: Optional[str] = None,
    db: Session = Depends(get_db),
):
    tasks, total = plugin_service.get_tasks(
        db,
        plugins=plugins,
        users=users,
        tags=tags,
        limit=limit,
        offset=(page - 1) * limit,
        include_full_input=include_full_input,
        include_output=include_output,
        since=since,
        order_by=order_by,
        order_direction=order_direction,
        status=status,
        q=query,
    )

    tasks_converted = list(
        map(
            lambda x: domain_to_dto_plugin_task(x, include_full_input, include_output),
            tasks,
        )
    )

    return PluginTasks(
        records=tasks_converted,
        page=page,
        total_pages=math.ceil(total / limit),
        limit=limit,
        total=total,
    )


@router.get("/{plugin_id}/tasks", response_model=PluginTasks)
async def read_tasks(
    limit: int = -1,
    page: int = 1,
    include_full_input: bool = False,
    include_output: bool = True,
    since: Optional[datetime] = None,
    order_by: PluginTaskOrderOptions = PluginTaskOrderOptions.id,
    order_direction: OrderDirection = OrderDirection.desc,
    status: Optional[PluginTaskStatus] = None,
    users: Optional[List[int]] = Query(None),
    tags: Optional[List[TagStr]] = Query(None),
    db: Session = Depends(get_db),
    plugin=Depends(get_plugin),
    query: Optional[str] = None,
):
    tasks, total = plugin_service.get_tasks(
        db,
        plugins=[plugin.info["Name"]],
        users=users,
        tags=tags,
        limit=limit,
        offset=(page - 1) * limit,
        include_full_input=include_full_input,
        include_output=include_output,
        since=since,
        order_by=order_by,
        order_direction=order_direction,
        status=status,
        q=query,
    )

    tasks_converted = list(
        map(
            lambda x: domain_to_dto_plugin_task(x, include_full_input, include_output),
            tasks,
        )
    )

    return PluginTasks(
        records=tasks_converted,
        page=page,
        total_pages=math.ceil(total / limit) if limit > 0 else page,
        limit=limit,
        total=total,
    )


@router.get("/{plugin_id}/tasks/{uid}", response_model=PluginTask)
async def read_task(
    uid: int,
    db: Session = Depends(get_db),
    plugin=Depends(get_plugin),
    db_task: models.PluginTask = Depends(get_task),
):
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")

    return domain_to_dto_plugin_task(db_task)
