from typing import List, Optional

from pydantic import BaseModel

from empire.server.core.db import models


def domain_to_dto_process(process: models.HostProcess):
    if process.agent:
        agent_id = process.agent.session_id
    else:
        agent_id = None

    return Process(
        process_id=process.process_id,
        process_name=process.process_name,
        host_id=process.host_id,
        architecture=process.architecture,
        user=process.user,
        stale=process.stale,
        agent_id=agent_id,
    )


class Process(BaseModel):
    process_id: int
    process_name: str
    host_id: int
    architecture: Optional[str]
    user: Optional[str]
    stale: bool
    agent_id: Optional[str]


class Processes(BaseModel):
    records: List[Process]
