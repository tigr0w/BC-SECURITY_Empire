from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel

from empire.server.database import models
from empire.server.v2.api.shared_dto import PROXY_ID


def domain_to_dto_agent(agent: models.Agent):
    return Agent(
        session_id=agent.session_id,
        name=agent.name,
        # the way agents connect, we only get the name. Ideally we should
        # be getting the id so we can store it by id on the db.
        # Future change would be to add id to the dto and change
        # listener to listener_name
        # listener_id=agent.listener,
        listener=agent.listener,
        host_id=agent.host_id,
        hostname=agent.host.name,
        language=agent.language,
        language_version=agent.language_version,
        delay=agent.delay,
        jitter=agent.jitter,
        external_ip=agent.external_ip,
        internal_ip=agent.internal_ip,
        username=agent.username,
        high_integrity=agent.high_integrity,
        process_id=agent.process_id,
        process_name=agent.process_name,
        os_details=agent.os_details,
        nonce=agent.nonce,
        checkin_time=agent.checkin_time,
        lastseen_time=agent.lastseen_time,
        parent=agent.parent,
        children=agent.children,
        servers=agent.servers,
        profile=agent.profile,
        functions=agent.functions,
        kill_date=agent.kill_date,
        working_hours=agent.working_hours,
        lost_limit=agent.lost_limit,
        notes=agent.notes,
        architecture=agent.architecture,
        stale=agent.stale,
        archived=agent.archived,
        # Could make this a typed class later to match the schema
        proxies=to_proxy_dto(agent.proxies),
    )


def to_proxy_dto(proxies):
    if proxies:
        converted = []
        for p in proxies["proxies"]:
            p_copy = p.copy()
            p_copy["proxy_type"] = PROXY_ID[p["proxy_type"]]
            converted.append(p_copy)

        return {"proxies": converted}

    return {}


class Agent(BaseModel):
    session_id: str
    name: str
    # listener_id: int
    listener: str
    host_id: int
    hostname: str
    language: str
    language_version: str
    delay: int
    jitter: float
    external_ip: Optional[str]
    internal_ip: Optional[str]
    username: Optional[str]
    high_integrity: bool
    process_id: int
    process_name: str
    os_details: Optional[str]
    nonce: str
    checkin_time: datetime
    lastseen_time: datetime
    parent: Optional[str]
    children: Optional[str]
    servers: Optional[str]
    profile: Optional[str]
    functions: Optional[str]
    kill_date: Optional[str]
    working_hours: Optional[str]
    lost_limit: int
    notes: Optional[str]
    architecture: Optional[str]
    archived: bool
    stale: bool
    proxies: Optional[Dict]


class Agents(BaseModel):
    records: List[Agent]


class AgentUpdateRequest(BaseModel):
    name: str
    notes: Optional[str]
