from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from empire.server.database import models
from empire.server.server import main
from empire.server.v2.api.agent.agent_dto import (
    Agent,
    Agents,
    AgentUpdateRequest,
    domain_to_dto_agent,
)
from empire.server.v2.api.EmpireApiRouter import APIRouter
from empire.server.v2.api.jwt_auth import get_current_active_user
from empire.server.v2.api.shared_dependencies import get_db
from empire.server.v2.api.shared_dto import BadRequestResponse, NotFoundResponse

agent_service = main.agentsv2

router = APIRouter(
    prefix="/api/v2/agents",
    tags=["agents"],
    responses={
        404: {"description": "Not found", "model": NotFoundResponse},
        400: {"description": "Bad request", "model": BadRequestResponse},
    },
    dependencies=[Depends(get_current_active_user)],
)


async def get_agent(uid: str, db: Session = Depends(get_db)):
    agent = agent_service.get_by_id(db, uid)

    if agent:
        return agent

    raise HTTPException(404, f"Agent not found for id {uid}")


@router.get("/{uid}", response_model=Agent)
async def read_agent(uid: str, db_agent: models.Agent = Depends(get_agent)):
    return domain_to_dto_agent(db_agent)


@router.get("/", response_model=Agents)
async def read_agents(
    db: Session = Depends(get_db),
    include_archived: bool = False,
    include_stale: bool = True,
):
    agents = list(
        map(
            lambda x: domain_to_dto_agent(x),
            agent_service.get_all(db, include_archived, include_stale),
        )
    )

    return {"records": agents}


@router.put("/{uid}", response_model=Agent)
async def update_agent(
    uid: str,
    agent_req: AgentUpdateRequest,
    db: Session = Depends(get_db),
    db_agent: models.Agent = Depends(get_agent),
):
    resp, err = agent_service.update_agent(db, db_agent, agent_req)

    if err:
        raise HTTPException(status_code=400, detail=err)

    return domain_to_dto_agent(resp)
