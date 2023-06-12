import logging
import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

log = logging.getLogger(__name__)


@pytest.fixture(scope="function", autouse=True)
def agents(session_local, models, host):
    with session_local.begin() as db:
        db_host = db.query(models.Host).filter(models.Host.id == host).first()
        agent = models.Agent(
            name="TEST123",
            session_id="TEST123",
            delay=60,
            jitter=0.1,
            internal_ip=db_host.internal_ip,
            external_ip="1.1.1.1",
            session_key="qwerty",
            nonce="nonce",
            profile="profile",
            kill_date="killDate",
            working_hours="workingHours",
            lost_limit=60,
            listener="http",
            language="powershell",
            language_version="5",
            high_integrity=False,
            process_name="proc",
            process_id=12345,
            hostname="vinnybod",
            host_id=host,
            archived=False,
        )

        agent2 = models.Agent(
            name="SECOND",
            session_id="SECOND",
            delay=60,
            jitter=0.1,
            internal_ip=db_host.internal_ip,
            external_ip="1.1.1.1",
            session_key="qwerty",
            nonce="nonce",
            profile="profile",
            kill_date="killDate",
            working_hours="workingHours",
            lost_limit=60,
            listener="http",
            language="powershell",
            language_version="5",
            high_integrity=False,
            process_name="proc",
            process_id=12345,
            hostname="vinnybod",
            host_id=host,
            archived=False,
        )

        agent3 = models.Agent(
            name="archived",
            session_id="archived",
            delay=60,
            jitter=0.1,
            internal_ip=db_host.internal_ip,
            external_ip="1.1.1.1",
            session_key="qwerty",
            nonce="nonce",
            profile="profile",
            kill_date="killDate",
            working_hours="workingHours",
            lost_limit=60,
            listener="http",
            language="powershell",
            language_version="5",
            high_integrity=False,
            process_name="proc",
            process_id=12345,
            hostname="vinnybod",
            host_id=host,
            archived=True,
        )

        agent4 = models.Agent(
            name="STALE",
            session_id="STALE",
            delay=1,
            jitter=0.1,
            internal_ip=db_host.internal_ip,
            external_ip="1.1.1.1",
            session_key="qwerty",
            nonce="nonce",
            profile="profile",
            kill_date="killDate",
            working_hours="workingHours",
            lost_limit=60,
            listener="http",
            language="powershell",
            language_version="5",
            high_integrity=False,
            process_name="proc",
            process_id=12345,
            hostname="vinnybod",
            host_id=host,
            archived=False,
        )

        db.add(agent)
        db.add(agent2)
        db.add(agent3)
        db.add(agent4)
        db.add(models.AgentCheckIn(agent_id=agent.session_id))
        db.add(models.AgentCheckIn(agent_id=agent2.session_id))
        db.add(models.AgentCheckIn(agent_id=agent3.session_id))
        db.add(
            models.AgentCheckIn(
                agent_id=agent4.session_id,
                checkin_time=datetime.now(timezone.utc) - timedelta(days=2),
            )
        )
        db.flush()
        agents = [agent, agent2, agent3, agent4]

        agent_ids = [agent.session_id for agent in agents]

    yield agent_ids

    with session_local.begin() as db:
        db.query(models.Agent).delete()


def test_stale_expression(empire_config):
    from empire.server.core.db import models
    from empire.server.core.db.base import SessionLocal

    db = SessionLocal()

    # assert all 4 agents are in the database
    agents = db.query(models.Agent).all()
    assert len(agents) == 4

    # assert one of the agents is stale via its hybrid property
    assert any(agent.stale for agent in agents)

    # assert we can filter on stale via the hybrid expression
    stale = (
        db.query(models.Agent).filter(models.Agent.stale == True).all()  # noqa: E712
    )
    assert len(stale) == 1

    # assert we can filter on stale via the hybrid expression
    not_stale = (
        db.query(models.Agent).filter(models.Agent.stale == False).all()  # noqa: E712
    )
    assert len(not_stale) == 3


def test_large_internal_ip_works(session_local, host, models, agent):
    with session_local.begin() as db:
        db_agent = (
            db.query(models.Agent).filter(models.Agent.session_id == agent).first()
        )
        db_host = db.query(models.Host).filter(models.Host.id == host).first()
        db_agent.internal_ip = "192.168.1.75 fe90::51e7:5dc7:be5d:b22e 3600:1900:7bb0:90d0:4d3c:2cd6:3fe:883b 5600:1900:3aa0:80d1:18a4:4431:5023:eef7 6600:1500:1aa0:20d0:fd69:26ff:5c4c:8d27 2900:2700:4aa0:80d0::47 192.168.214.1 fe90::a24c:82de:578b:8626 192.168.245.1 fe00::f321:a1e:18d3:ab9"

        db.flush()

        db_host.internal_ip = db_agent.internal_ip

        db.flush()


def test_duplicate_host(session_local, models, host):
    with pytest.raises(IntegrityError), session_local.begin() as db:
        db_host = db.query(models.Host).filter(models.Host.id == host).first()
        host2 = models.Host(name=db_host.name, internal_ip=db_host.internal_ip)

        db.add(host2)
        db.flush()


def test_duplicate_checkin_raises_exception(session_local, models, agent):
    with pytest.raises(IntegrityError), session_local.begin() as db:
        db_agent = (
            db.query(models.Agent).filter(models.Agent.session_id == agent).first()
        )
        timestamp = datetime.now(timezone.utc)
        checkin = models.AgentCheckIn(
            agent_id=db_agent.session_id, checkin_time=timestamp
        )
        checkin2 = models.AgentCheckIn(
            agent_id=db_agent.session_id, checkin_time=timestamp
        )

        db.add(checkin)
        db.add(checkin2)
        db.flush()


def test_can_ignore_duplicate_checkins(session_local, models, agent, main):
    with session_local.begin() as db:
        db_agent = (
            db.query(models.Agent).filter(models.Agent.session_id == agent).first()
        )
        prev_checkin_count = len(db_agent.checkins.all())
        # Need to ensure that these two checkins are not the same second
        # as the original checkin
        time.sleep(2)

        main.agents.update_agent_lastseen_db(db_agent.session_id, db)
        main.agents.update_agent_lastseen_db(db_agent.session_id, db)

    with session_local.begin() as db:
        db_agent = (
            db.query(models.Agent).filter(models.Agent.session_id == agent).first()
        )
        checkin_count = len(db_agent.checkins.all())

        assert checkin_count == prev_checkin_count + 1
