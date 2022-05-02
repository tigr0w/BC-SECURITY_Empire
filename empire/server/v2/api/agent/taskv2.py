import base64
import math
from datetime import datetime
from typing import List, Optional

from fastapi import Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session
from starlette.responses import Response
from starlette.status import HTTP_204_NO_CONTENT

from empire.server.database import models
from empire.server.database.models import TaskingStatus
from empire.server.server import main
from empire.server.v2.api.agent.task_dto import (
    CommsPostRequest,
    DirectoryListPostRequest,
    DownloadPostRequest,
    ExitPostRequest,
    KillDatePostRequest,
    ModulePostRequest,
    ProxyListPostRequest,
    ScriptCommandPostRequest,
    ShellPostRequest,
    SleepPostRequest,
    SysinfoPostRequest,
    Task,
    TaskOrderOptions,
    Tasks,
    UploadPostRequest,
    WorkingHoursPostRequest,
    domain_to_dto_task,
)
from empire.server.v2.api.EmpireApiRouter import APIRouter
from empire.server.v2.api.jwt_auth import get_current_active_user, get_current_user
from empire.server.v2.api.shared_dependencies import get_db
from empire.server.v2.api.shared_dto import OrderDirection
from empire.server.v2.core.agent_service import AgentService
from empire.server.v2.core.agent_task_service import AgentTaskService
from empire.server.v2.core.download_service import DownloadService

agent_task_service: AgentTaskService = main.agenttasksv2
agent_service: AgentService = main.agentsv2
download_service: DownloadService = main.downloadsv2

router = APIRouter(
    prefix="/api/v2beta/agents",
    tags=["agents", "tasks"],
    responses={404: {"description": "Not found"}},
    dependencies=[Depends(get_current_active_user)],
)


# Set proxy IDs
PROXY_NAME = {
    "SOCKS4": 1,
    "SOCKS5": 2,
    "HTTP": 3,
    "SSL": 4,
    "SSL_WEAK": 5,
    "SSL_ANON": 6,
    "TOR": 7,
    "HTTPS": 8,
    "HTTP_CONNECT": 9,
    "HTTPS_CONNECT": 10,
}

# inverse of PROXY_NAME
PROXY_ID = {v: k for k, v in PROXY_NAME.items()}


async def get_agent(agent_id: str, db: Session = Depends(get_db)):
    agent = agent_service.get_by_id(db, agent_id)

    if agent:
        return agent

    raise HTTPException(404, f"Agent not found for id {agent_id}")


async def get_task(
    uid: int, db: Session = Depends(get_db), db_agent: models.Agent = Depends(get_agent)
):
    task = agent_task_service.get_task_for_agent(db, db_agent.session_id, uid)

    if task:
        return task

    raise HTTPException(
        404, f"Task not found for agent {db_agent.session_id} and task id {uid}"
    )


@router.get("/tasks", response_model=Tasks)
async def get_tasks_all_agents(
    limit: int = -1,
    page: int = 1,
    include_full_input: bool = False,
    include_original_output: bool = False,
    include_output: bool = True,
    since: Optional[datetime] = None,
    order_by: TaskOrderOptions = TaskOrderOptions.id,
    order_direction: OrderDirection = OrderDirection.desc,
    status: Optional[TaskingStatus] = None,
    agents: Optional[List[str]] = Query(None),
    users: Optional[List[int]] = Query(None),
    db: Session = Depends(get_db),
):
    tasks, total = agent_task_service.get_tasks(
        db,
        agents=agents,
        users=users,
        limit=limit,
        offset=(page - 1) * limit,
        include_full_input=include_full_input,
        include_original_output=include_original_output,
        include_output=include_output,
        since=since,
        order_by=order_by,
        order_direction=order_direction,
        status=status,
    )

    tasks_converted = list(
        map(
            lambda x: domain_to_dto_task(
                x, include_full_input, include_original_output, include_output
            ),
            tasks,
        )
    )

    return Tasks(
        records=tasks_converted,
        page=page,
        total_pages=math.ceil(total / limit),
        limit=limit,
        total=total,
    )


@router.get("/{agent_id}/tasks", response_model=Tasks)
async def read_tasks(
    limit: int = -1,
    page: int = 1,
    include_full_input: bool = False,
    include_original_output: bool = False,
    include_output: bool = True,
    since: Optional[datetime] = None,
    order_by: TaskOrderOptions = TaskOrderOptions.id,
    order_direction: OrderDirection = OrderDirection.desc,
    status: Optional[TaskingStatus] = None,
    users: Optional[List[int]] = Query(None),
    db: Session = Depends(get_db),
    db_agent: models.Agent = Depends(get_agent),
):
    tasks, total = agent_task_service.get_tasks(
        db,
        agents=[db_agent.session_id],
        users=users,
        limit=limit,
        offset=(page - 1) * limit,
        include_full_input=include_full_input,
        include_original_output=include_original_output,
        include_output=include_output,
        since=since,
        order_by=order_by,
        order_direction=order_direction,
        status=status,
    )

    tasks_converted = list(
        map(
            lambda x: domain_to_dto_task(
                x, include_full_input, include_original_output, include_output
            ),
            tasks,
        )
    )

    return Tasks(
        records=tasks_converted,
        page=page,
        total_pages=math.ceil(total / limit),
        limit=limit,
        total=total,
    )


@router.get("/{agent_id}/tasks/{uid}", response_model=Task)
async def read_task(
    uid: int,
    db: Session = Depends(get_db),
    db_agent: models.Agent = Depends(get_agent),
    db_task: models.Tasking = Depends(get_task),
):
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")

    return domain_to_dto_task(db_task)


@router.post("/{agent_id}/tasks/shell", status_code=201, response_model=Task)
async def create_task_shell(
    shell_request: ShellPostRequest,
    db_agent: models.Agent = Depends(get_agent),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    resp, err = agent_task_service.create_task_shell(
        db, db_agent, shell_request.command, current_user.id
    )

    if err:
        raise HTTPException(status_code=400, detail=err)

    return domain_to_dto_task(resp)


@router.post("/{agent_id}/tasks/module", status_code=201, response_model=Task)
async def create_task_module(
    module_request: ModulePostRequest,
    db_agent: models.Agent = Depends(get_agent),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    resp, err = agent_task_service.create_task_module(
        db, db_agent, module_request, current_user.id
    )

    if err:
        raise HTTPException(status_code=400, detail=err)

    return domain_to_dto_task(resp)


@router.post("/{agent_id}/tasks/upload", status_code=201, response_model=Task)
async def create_task_upload(
    upload_request: UploadPostRequest,
    db_agent: models.Agent = Depends(get_agent),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    download = download_service.get_by_id(db, upload_request.file_id)

    if not download:
        raise HTTPException(
            status_code=400,
            detail=f"Download not found for id {upload_request.file_id}",
        )

    with open(download.location, "rb") as f:
        file_data = f.read()

    file_data = base64.b64encode(file_data).decode("UTF-8")
    raw_data = base64.b64decode(file_data)

    # Todo: We can probably remove this file size limit with updates to the agent code.
    #  At the moment the data is expected as a string of "filename|filedata"
    #  We could instead take a larger file, store it as a file on the server and store a reference to it in the db.
    #  And then change the way the agents pull down the file.
    if len(raw_data) > 1048576:
        raise HTTPException(
            status_code=400, detail="file size too large. Maximum file size of 1MB"
        )

    resp, err = agent_task_service.create_task_upload(
        db, db_agent, file_data, upload_request.path_to_file, current_user.id
    )

    if err:
        raise HTTPException(status_code=400, detail=err)

    return domain_to_dto_task(resp)


@router.post("/{agent_id}/tasks/download", status_code=201, response_model=Task)
async def create_task_download(
    download_request: DownloadPostRequest,
    db_agent: models.Agent = Depends(get_agent),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    resp, err = agent_task_service.create_task_download(
        db, db_agent, download_request.path_to_file, current_user.id
    )

    if err:
        raise HTTPException(status_code=400, detail=err)

    return domain_to_dto_task(resp)


@router.post("/{agent_id}/tasks/script_import", status_code=201, response_model=Task)
async def create_task_script_import(
    file: UploadFile = File(...),
    db_agent: models.Agent = Depends(get_agent),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    file_data = await file.read()
    file_data = file_data.decode("utf-8")
    resp, err = agent_task_service.create_task_script_import(
        db, db_agent, file_data, current_user.id
    )

    if err:
        raise HTTPException(status_code=400, detail=err)

    return domain_to_dto_task(resp)


@router.post("/{agent_id}/tasks/script_command", status_code=201, response_model=Task)
async def create_task_script_command(
    script_command_request: ScriptCommandPostRequest,
    db_agent: models.Agent = Depends(get_agent),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    For python agents, this will run a script on the agent.
    For Powershell agents, script_import must be run first and then this will run the script.

    :param script_command_request:
    :param db_agent:
    :param db:
    :param current_user:
    :return:
    """
    resp, err = agent_task_service.create_task_script_command(
        db, db_agent, script_command_request.command, current_user.id
    )

    if err:
        raise HTTPException(status_code=400, detail=err)

    return domain_to_dto_task(resp)


@router.post("/{agent_id}/tasks/sysinfo", status_code=201, response_model=Task)
async def create_task_sysinfo(
    sysinfo_request: SysinfoPostRequest,  # todo empty atm
    db_agent: models.Agent = Depends(get_agent),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    resp, err = agent_task_service.create_task_sysinfo(db, db_agent, current_user.id)

    if err:
        raise HTTPException(status_code=400, detail=err)

    return domain_to_dto_task(resp)


@router.post("/{agent_id}/tasks/update_comms", status_code=201, response_model=Task)
async def create_task_update_comms(
    comms_request: CommsPostRequest,
    db_agent: models.Agent = Depends(get_agent),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    resp, err = agent_task_service.create_task_update_comms(
        db, db_agent, comms_request.new_listener_id, current_user.id
    )

    if err:
        raise HTTPException(status_code=400, detail=err)

    return domain_to_dto_task(resp)


@router.post("/{agent_id}/tasks/sleep", status_code=201, response_model=Task)
async def create_task_update_sleep(
    sleep_request: SleepPostRequest,
    db_agent: models.Agent = Depends(get_agent),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    resp, err = agent_task_service.create_task_update_sleep(
        db, db_agent, sleep_request.delay, sleep_request.jitter, current_user.id
    )

    if err:
        raise HTTPException(status_code=400, detail=err)

    return domain_to_dto_task(resp)


@router.post("/{agent_id}/tasks/kill_date", status_code=201, response_model=Task)
async def create_task_update_kill_date(
    kill_date_request: KillDatePostRequest,
    db_agent: models.Agent = Depends(get_agent),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    resp, err = agent_task_service.create_task_update_kill_date(
        db, db_agent, kill_date_request.kill_date, current_user.id
    )

    if err:
        raise HTTPException(status_code=400, detail=err)

    return domain_to_dto_task(resp)


@router.post("/{agent_id}/tasks/working_hours", status_code=201, response_model=Task)
async def create_task_update_working_hours(
    working_hours_request: WorkingHoursPostRequest,
    db_agent: models.Agent = Depends(get_agent),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    resp, err = agent_task_service.create_task_update_working_hours(
        db, db_agent, working_hours_request.working_hours, current_user.id
    )

    if err:
        raise HTTPException(status_code=400, detail=err)

    return domain_to_dto_task(resp)


@router.post("/{agent_id}/tasks/directory_list", status_code=201, response_model=Task)
async def create_task_update_directory_list(
    directory_list_request: DirectoryListPostRequest,
    db_agent: models.Agent = Depends(get_agent),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    resp, err = agent_task_service.create_task_directory_list(
        db, db_agent, directory_list_request.path, current_user.id
    )

    if err:
        raise HTTPException(status_code=400, detail=err)

    return domain_to_dto_task(resp)


@router.post("/{agent_id}/tasks/proxy_list", status_code=201, response_model=Task)
async def create_task_update_proxy_list(
    proxy_list_request: ProxyListPostRequest,
    db_agent: models.Agent = Depends(get_agent),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # We have to use a string enum to get the api to accept strings
    #  then convert to int manually
    proxy_list_dict = proxy_list_request.dict()
    for proxy in proxy_list_dict["proxies"]:
        proxy["proxy_type"] = PROXY_NAME[proxy["proxy_type"]]
    resp, err = agent_task_service.create_task_proxy_list(
        db, db_agent, proxy_list_dict, current_user.id
    )

    if err:
        raise HTTPException(status_code=400, detail=err)

    return domain_to_dto_task(resp)


@router.post("/{agent_id}/tasks/exit", status_code=201, response_model=Task)
async def create_task_exit(
    exit_request: ExitPostRequest,
    db_agent: models.Agent = Depends(get_agent),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    resp, err = agent_task_service.create_task_exit(db, db_agent, current_user.id)

    if err:
        raise HTTPException(status_code=400, detail=err)

    return domain_to_dto_task(resp)


@router.delete(
    "/{agent_id}/tasks/{uid}", status_code=HTTP_204_NO_CONTENT, response_class=Response
)
async def delete_task(
    uid: int, db: Session = Depends(get_db), db_task: models.Tasking = Depends(get_task)
):
    if db_task.status != TaskingStatus.queued:
        raise HTTPException(
            status_code=400, detail="Task must be in a queued state to be deleted"
        )

    agent_task_service.delete_task(db, db_task)
