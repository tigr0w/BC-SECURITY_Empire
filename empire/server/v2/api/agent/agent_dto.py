from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel


def domain_to_dto_agent(agent):
    return Agent(
        session_id=agent.session_id,
        name=agent.name,
        listener=agent.listener,
        host=agent.host_id,
        language=agent.language,
        language_version=agent.language_version,
        delay=agent.delay,
        jitter=agent.jitter,
        external_ip=agent.external_ip,
        internal_ip=agent.internal_ip,
        username=agent.username,
        high_integrity=agent.high_integrity,
        process_name=agent.process_name,
        process_id=agent.process_id,
        hostname=agent.hostname,
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
        # todo could make this a typed class later to match the schema
        #  this still needs work because while the task accepts string for proxy type
        #  this returns int. We can avoid the stupid mapping of the agents just use the string values instead.
        proxies=agent.proxy,
    )


class Agent(BaseModel):
    session_id: str
    name: str
    listener: str  # todo expand?
    host: str  # todo expand?
    language: str
    language_version: str
    delay: int
    jitter: float
    external_ip: Optional[str]
    internal_ip: Optional[str]
    username: Optional[str]
    high_integrity: bool
    process_name: str
    process_id: int
    hostname: str  # todo dont need if expanding host
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
