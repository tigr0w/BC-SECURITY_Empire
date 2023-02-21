from typing import List, Optional, Tuple

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from empire.server.api.api_router import APIRouter
from empire.server.api.jwt_auth import get_current_active_user
from empire.server.api.v2.agent.agent_file_dto import AgentFile, domain_to_dto_file
from empire.server.api.v2.shared_dependencies import get_db
from empire.server.api.v2.shared_dto import BadRequestResponse, NotFoundResponse
from empire.server.core.agent_file_service import AgentFileService
from empire.server.core.agent_service import AgentService
from empire.server.core.db import models
from empire.server.server import main

agent_file_service: AgentFileService = main.agentfilesv2
agent_service: AgentService = main.agentsv2

router = APIRouter(
    prefix="/api/v2/agents/{agent_id}/files",
    tags=["agents"],
    responses={
        404: {"description": "Not found", "model": NotFoundResponse},
        400: {"description": "Bad request", "model": BadRequestResponse},
    },
    dependencies=[Depends(get_current_active_user)],
)


async def get_agent(agent_id: str, db: Session = Depends(get_db)):
    agent = agent_service.get_by_id(db, agent_id)

    if agent:
        return agent

    raise HTTPException(404, f"Agent not found for id {agent_id}")


async def get_file(
    uid: int, db: Session = Depends(get_db), db_agent: models.Agent = Depends(get_agent)
):
    file = agent_file_service.get_file(db, db_agent.session_id, uid)

    if file:
        return file

    raise HTTPException(
        404, f"File not found for agent {db_agent.session_id} and file id {uid}"
    )


@router.get("/root", dependencies=[Depends(get_current_active_user)])
async def read_file_root(
    db: Session = Depends(get_db), db_agent: models.Agent = Depends(get_agent)
):
    file = agent_file_service.get_file_by_path(db, db_agent.session_id, "/")

    if file:
        return domain_to_dto_file(*file)

    raise HTTPException(
        404, f'File not found for agent {db_agent.session_id} and file path "/"'
    )


@router.get(
    "/{uid}", response_model=AgentFile, dependencies=[Depends(get_current_active_user)]
)
async def read_file(
    uid: int,
    db_agent: models.Agent = Depends(get_agent),
    db_file: Optional[Tuple[models.AgentFile, List[models.AgentFile]]] = Depends(
        get_file
    ),
):
    if db_file:
        return domain_to_dto_file(*db_file)

    raise HTTPException(
        404, f'File not found for agent {db_agent.session_id} and file path "/"'
    )
