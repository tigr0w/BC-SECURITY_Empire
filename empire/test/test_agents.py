from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture(scope="module", autouse=True)
def agent():
    from empire.server.core.db import models
    from empire.server.core.db.base import SessionLocal

    db = SessionLocal()
    hosts = db.query(models.Host).all()
    if len(hosts) == 0:
        host = models.Host(name="default_host", internal_ip="127.0.0.1")
    else:
        host = hosts[0]

    agents = db.query(models.Agent).all()
    if len(agents) == 0:
        agent = models.Agent(
            name="TEST123",
            session_id="TEST123",
            delay=60,
            jitter=0.1,
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
            host=host,
            archived=False,
        )

        agent2 = models.Agent(
            name="SECOND",
            session_id="SECOND",
            delay=60,
            jitter=0.1,
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
            host=host,
            archived=False,
        )

        agent3 = models.Agent(
            name="archived",
            session_id="archived",
            delay=60,
            jitter=0.1,
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
            host=host,
            archived=True,
        )

        agent4 = models.Agent(
            name="STALE",
            session_id="STALE",
            delay=1,
            jitter=0.1,
            external_ip="1.1.1.1",
            session_key="qwerty",
            nonce="nonce",
            profile="profile",
            kill_date="killDate",
            working_hours="workingHours",
            lastseen_time=datetime.now(timezone.utc) - timedelta(days=2),
            lost_limit=60,
            listener="http",
            language="powershell",
            language_version="5",
            high_integrity=False,
            process_name="proc",
            process_id=12345,
            hostname="vinnybod",
            host=host,
            archived=False,
        )

        db.add(host)
        db.add(agent)
        db.add(agent2)
        db.add(agent3)
        db.add(agent4)
        db.flush()
        db.commit()
        agents = [agent, agent2, agent3, agent4]

    yield agents

    db = Session()
    db.delete(agents[0])
    db.delete(agents[1])
    db.delete(agents[2])
    db.delete(agents[3])
    db.delete(host)
    db.commit()


def test_stale_expression():
    from empire.server.core.db import models
    from empire.server.core.db.base import SessionLocal

    db = SessionLocal()

    # assert all 4 agents are in the database
    agents = db.query(models.Agent).all()
    assert len(agents) == 4

    # assert one of the agents is stale via its hybrid property
    assert any(agent.stale for agent in agents)

    # assert we can filter on stale via the hybrid expression
    stale = db.query(models.Agent).filter(models.Agent.stale == True).all()
    assert len(stale) == 1

    # assert we can filter on stale via the hybrid expression
    not_stale = db.query(models.Agent).filter(models.Agent.stale == False).all()
    assert len(not_stale) == 3
