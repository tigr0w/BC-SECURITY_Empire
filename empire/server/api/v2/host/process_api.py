from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from empire.server.api.api_router import APIRouter
from empire.server.api.jwt_auth import get_current_active_user
from empire.server.api.v2.host.process_dto import (
    Process,
    Processes,
    domain_to_dto_process,
)
from empire.server.api.v2.shared_dependencies import get_db
from empire.server.api.v2.shared_dto import BadRequestResponse, NotFoundResponse
from empire.server.core.db import models
from empire.server.server import main

host_process_service = main.processesv2
host_service = main.hostsv2

router = APIRouter(
    prefix="/api/v2/hosts/{host_id}/processes",
    tags=["hosts"],
    responses={
        404: {"description": "Not found", "model": NotFoundResponse},
        400: {"description": "Bad request", "model": BadRequestResponse},
    },
    dependencies=[Depends(get_current_active_user)],
)


async def get_host(host_id: int, db: Session = Depends(get_db)):
    host = host_service.get_by_id(db, host_id)

    if host:
        return host

    raise HTTPException(status_code=404, detail=f"Host not found for id {host_id}")


async def get_process(
    uid: int, db: Session = Depends(get_db), db_host: models.Host = Depends(get_host)
):
    process = host_process_service.get_process_for_host(db, db_host, uid)

    if process:
        return process

    raise HTTPException(
        404, f"Process not found for host id {db_host.id} and process id {uid}"
    )


@router.get("/{uid}", response_model=Process)
async def read_process(uid: int, db_process: models.HostProcess = Depends(get_process)):
    return domain_to_dto_process(db_process)


@router.get("/", response_model=Processes)
async def read_processes(
    db: Session = Depends(get_db), db_host: models.Host = Depends(get_host)
):
    processes = list(
        map(
            lambda x: domain_to_dto_process(x),
            host_process_service.get_processes_for_host(db, db_host),
        )
    )

    return {"records": processes}
