import logging
import queue

from sqlalchemy import and_
from sqlalchemy.orm import Session

from empire.server.common.helpers import KThread
from empire.server.common.socks import create_client, start_client
from empire.server.core.agent_task_service import AgentTaskService
from empire.server.core.db import models
from empire.server.core.db.base import SessionLocal

log = logging.getLogger(__name__)


class AgentService(object):
    def __init__(self, main_menu):
        self.main_menu = main_menu

        self.agent_task_service: AgentTaskService = main_menu.agenttasksv2

        self._start_existing_socks()

    @staticmethod
    def get_all(
        db: Session, include_archived: bool = False, include_stale: bool = True
    ):
        query = db.query(models.Agent).filter(
            models.Agent.host_id != ""
        )  # don't return agents that haven't fully checked in.

        if not include_archived:
            query = query.filter(models.Agent.archived == False)  # noqa: E712

        agents = query.all()

        # can't use the hybrid expression until the function in models.py is updated to support mysql.
        if not include_stale:
            agents = [agent for agent in agents if not agent.stale]

        return agents

    @staticmethod
    def get_by_id(db: Session, uid: str):
        return db.query(models.Agent).filter(models.Agent.session_id == uid).first()

    @staticmethod
    def get_by_name(db: Session, name: str):
        return db.query(models.Agent).filter(models.Agent.name == name).first()

    def update_agent(self, db: Session, db_agent: models.Agent, agent_req):
        if agent_req.name != db_agent.name:
            if not self.get_by_name(db, agent_req.name):
                db_agent.name = agent_req.name
            else:
                return None, f"Agent with name {agent_req.name} already exists."

        db_agent.notes = agent_req.notes

        return db_agent, None

    def start_existing_socks(self, db: Session, agent: models.Agent):
        log.info(f"Starting SOCKS client for {agent.session_id}")
        try:
            self.main_menu.agents.socksqueue[agent.session_id] = queue.Queue()
            client = create_client(
                self.main_menu,
                self.main_menu.agents.socksqueue[agent.session_id],
                agent.session_id,
            )
            self.main_menu.agents.socksthread[agent.session_id] = KThread(
                target=start_client,
                args=(client, agent.socks_port),
            )

            self.main_menu.agents.socksclient[agent.session_id] = client
            self.main_menu.agents.socksthread[agent.session_id].daemon = True
            self.main_menu.agents.socksthread[agent.session_id].start()
            log.info(f'SOCKS client for "{agent.name}" successfully started')
        except Exception:
            log.error(f'SOCKS client for "{agent.name}" failed to start')

    def _start_existing_socks(self):
        with SessionLocal.begin() as db:
            agents = (
                db.query(models.Agent)
                .filter(
                    and_(
                        models.Agent.socks == True,  # noqa: E712
                        models.Agent.archived == False,  # noqa: E712
                    )
                )
                .all()
            )
            for agent in agents:
                self.start_existing_socks(db, agent)
