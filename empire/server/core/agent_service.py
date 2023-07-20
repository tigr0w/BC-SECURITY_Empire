import logging
import queue
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from empire.server.api.v2.agent.agent_dto import AggregateBucket
from empire.server.api.v2.shared_dto import OrderDirection
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

        if not include_stale:
            query = query.filter(models.Agent.stale == False)  # noqa: E712

        agents = query.all()

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

    @staticmethod
    def get_agent_checkins(
        db: Session,
        agents: List[str] = None,
        limit: int = -1,
        offset: int = 0,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        order_direction: OrderDirection = OrderDirection.desc,
    ):
        query = db.query(
            models.AgentCheckIn,
            func.count(models.AgentCheckIn.checkin_time).over().label("total"),
        )

        if agents:
            query = query.filter(models.AgentCheckIn.agent_id.in_(agents))

        if start_date:
            query = query.filter(models.AgentCheckIn.checkin_time >= start_date)

        if end_date:
            query = query.filter(models.AgentCheckIn.checkin_time <= end_date)

        if order_direction == OrderDirection.asc:
            query = query.order_by(models.AgentCheckIn.checkin_time.asc())
        else:
            query = query.order_by(models.AgentCheckIn.checkin_time.desc())

        if limit > 0:
            query = query.limit(limit).offset(offset)

        results = query.all()

        total = 0 if len(results) == 0 else results[0].total
        results = list(map(lambda x: x[0], results))

        return results, total

    @staticmethod
    def get_agent_checkins_aggregate(
        db: Session,
        agents: List[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        bucket_size: AggregateBucket = None,
    ):
        """
        Returns a list of checkin counts for the given agents, start_date, end_date, and bucket_size.
        This will raise a database exception if the empire server is using SQLite.
        Additional work could be done to build a query for SQLite, but I don't think it's worth the effort,
        given that we are moving towards a more robust database.
        """
        hour_format = {"sql": "%Y-%m-%d %H:00:00Z", "python": "%Y-%m-%d %H:00:00Z"}
        minute_format = {"sql": "%Y-%m-%d %H:%i:00Z", "python": "%Y-%m-%d %H:%M:00Z"}
        second_format = {"sql": "%Y-%m-%d %H:%i:%sZ", "python": "%Y-%m-%d %H:%M:%SZ"}
        day_format = {"sql": "%Y-%m-%d", "python": "%Y-%m-%d"}
        if bucket_size == AggregateBucket.hour:
            format = hour_format
        elif bucket_size == AggregateBucket.minute:
            format = minute_format
        elif bucket_size == AggregateBucket.second:
            format = second_format
        else:
            format = day_format

        time_agg = func.date_format(models.AgentCheckIn.checkin_time, format["sql"])

        query = db.query(
            time_agg.label("time_agg"),
            func.count(models.AgentCheckIn.checkin_time).label("count"),
        )

        if agents:
            query = query.filter(models.AgentCheckIn.agent_id.in_(agents))

        if start_date:
            query = query.filter(models.AgentCheckIn.checkin_time >= start_date)

        if end_date:
            query = query.filter(models.AgentCheckIn.checkin_time <= end_date)

        query = query.group_by("time_agg")

        results = query.all()
        converted_results = []

        for result in results:
            converted_results.append(
                {
                    "checkin_time": datetime.strptime(
                        result[0], format["python"]
                    ).replace(tzinfo=timezone.utc),
                    "count": result[1],
                }
            )

        return converted_results

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
