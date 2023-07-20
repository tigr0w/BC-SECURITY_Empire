import math
from datetime import datetime
from typing import List, Optional

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from empire.server.api.api_router import APIRouter
from empire.server.api.jwt_auth import get_current_active_user
from empire.server.api.v2.agent.agent_dto import (
    Agent,
    AgentCheckIns,
    AgentCheckInsAggregate,
    Agents,
    AgentUpdateRequest,
    AggregateBucket,
    domain_to_dto_agent,
    domain_to_dto_agent_checkin,
    domain_to_dto_agent_checkin_agg,
)
from empire.server.api.v2.shared_dependencies import get_db
from empire.server.api.v2.shared_dto import (
    BadRequestResponse,
    NotFoundResponse,
    OrderDirection,
)
from empire.server.core.config import empire_config
from empire.server.core.db import models
from empire.server.server import main

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


@router.get("/checkins", response_model=AgentCheckIns)
def read_agent_checkins_all(
    db: Session = Depends(get_db),
    agents: List[str] = Query(None),
    limit: int = 1000,
    page: int = 1,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    order_direction: OrderDirection = OrderDirection.desc,
):
    checkins, total = agent_service.get_agent_checkins(
        db, agents, limit, (page - 1) * limit, start_date, end_date, order_direction
    )
    checkins = list(map(lambda x: domain_to_dto_agent_checkin(x), checkins))

    return AgentCheckIns(
        records=checkins,
        page=page,
        total_pages=math.ceil(total / limit),
        limit=limit,
        total=total,
    )


@router.get("/checkins/aggregate", response_model=AgentCheckInsAggregate)
def read_agent_checkins_aggregate(
    db: Session = Depends(get_db),
    agents: List[str] = Query(None),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    bucket_size: Optional[AggregateBucket] = AggregateBucket.day,
):
    if empire_config.database.use == "sqlite":
        raise HTTPException(
            400,
            "Aggregate checkins not supported with sqlite. Please use MySQL.",
        )

    checkins = agent_service.get_agent_checkins_aggregate(
        db, agents, start_date, end_date, bucket_size
    )
    checkins = list(map(lambda x: domain_to_dto_agent_checkin_agg(x), checkins))

    return AgentCheckInsAggregate(
        records=checkins,
        start_date=start_date,
        end_date=end_date,
        bucket_size=bucket_size,
    )


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


@router.get("/{uid}/checkins", response_model=AgentCheckIns)
def read_agent_checkins(
    db: Session = Depends(get_db),
    db_agent: models.Agent = Depends(get_agent),
    limit: int = -1,
    page: int = 1,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    order_direction: OrderDirection = OrderDirection.desc,
):
    checkins, total = agent_service.get_agent_checkins(
        db,
        [db_agent.session_id],
        limit,
        (page - 1) * limit,
        start_date,
        end_date,
        order_direction,
    )
    checkins = list(map(lambda x: domain_to_dto_agent_checkin(x), checkins))

    return AgentCheckIns(
        records=checkins,
        page=page,
        total_pages=math.ceil(total / limit),
        limit=limit,
        total=total,
    )
