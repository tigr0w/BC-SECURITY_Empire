from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from empire.server.database import models
from empire.server.server import main
from empire.server.v2.api.EmpireApiRouter import APIRouter
from empire.server.v2.api.host.host_dto import Host, Hosts, domain_to_dto_host
from empire.server.v2.api.jwt_auth import get_current_active_user
from empire.server.v2.api.shared_dependencies import get_db

host_service = main.hostsv2

router = APIRouter(
    prefix="/api/v2beta/hosts",
    tags=["hosts"],
    responses={404: {"description": "Not found"}},
    dependencies=[Depends(get_current_active_user)],
)


async def get_host(uid: int, db: Session = Depends(get_db)):
    host = host_service.get_by_id(db, uid)

    if host:
        return host

    raise HTTPException(status_code=404, detail=f"Host not found for id {uid}")


# todo expand agent join?
@router.get("/{uid}", response_model=Host)
async def read_host(uid: int, db_host: models.Host = Depends(get_host)):
    return domain_to_dto_host(db_host)


@router.get("/", response_model=Hosts)
async def read_hosts(db: Session = Depends(get_db)):
    hosts = list(map(lambda x: domain_to_dto_host(x), host_service.get_all(db)))

    return {"records": hosts}
