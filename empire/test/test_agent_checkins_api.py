import asyncio
import logging
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest

log = logging.getLogger(__name__)


@contextmanager
def timer():
    start = time.perf_counter()
    yield lambda: time.perf_counter() - start


@pytest.fixture(scope="function")
def agents(session_local, host, models):
    agent_ids = []
    with session_local.begin() as db:
        for n in range(agent_count):
            agent_id = f"agent_{n}"
            agent_ids.append(agent_id)
            default_agent(agent_id, models, db, host)
            log.info(f"agent_{n}")

    yield agent_ids

    with session_local.begin() as db:
        db.query(models.AgentCheckIn).delete()
        db.query(models.Agent).delete()


def default_agent(session_id, models, db, host):
    db.add(
        models.Agent(
            name=session_id,
            session_id=session_id,
            delay=60,
            jitter=0.1,
            internal_ip="1.2.3.4",
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
    )


async def _create_checkins(session_local, models, agent_ids):
    await asyncio.gather(
        *[_create_checkin(session_local, models, agent_id) for agent_id in agent_ids]
    )


agent_count = 10
time_delta = 5  # 17280 checkins per agent per day
days_back = 7
end_time = datetime(2023, 1, 8, tzinfo=timezone.utc)
start_time = end_time - timedelta(days=days_back)


async def _create_checkin(session_local, models, agent_id):
    with session_local.begin() as db_2:
        checkins = []
        iter_time = start_time
        while iter_time < end_time:
            iter_time += timedelta(seconds=time_delta)
            checkins.append(
                models.AgentCheckIn(agent_id=agent_id, checkin_time=iter_time)
            )

        log.info(f"adding {len(checkins)} checkins for {agent_id}")
        db_2.add_all(checkins)


@pytest.mark.slow
def test_database_performance_checkins(models, host, agents, session_local):
    # logging.basicConfig()
    # logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
    # logging.getLogger("sqlalchemy.engine").propagate = True
    # print(query.statement.compile(compile_kwargs={"literal_binds": True}))

    with session_local() as db:
        asyncio.run(_create_checkins(session_local, models, agents))

        with timer() as t:
            checkins = db.query(models.AgentCheckIn).count()
            assert checkins >= (agent_count * 17280 * days_back)
        log.info(f"Time to query {checkins} checkins count: {t():0.4f} seconds")

        with timer() as t:
            agents = db.query(models.Agent).count()
            assert agents >= agent_count
        log.info(f"Time to query {agents} agents count: {t():0.4f} seconds")
        assert t() < 1

        with timer() as t:
            query = db.query(models.Agent)
            query.all()
        log.info(f"Time to query {agents} agents: {t():0.4f} seconds")
        assert t() < 1

        with timer() as t:
            query = db.query(models.AgentCheckIn).limit(100000)
            query.all()
        log.info(f"Time to query {checkins} checkins: {t():0.4f} seconds")
        # Changed from 4 to 5 in 2023/07
        assert t() < 5

        agents = db.query(models.Agent).all()

        with timer() as t:
            for a in agents:
                name = a.name
                lastseen_time = a.lastseen_time
                stale = a.stale
                log.info(f"{name} - {lastseen_time} - {stale}")
        log.info(f"Time to query {agents} agents' dynamic fields: {t():0.4f} seconds")
        assert t() < 0.1 * agent_count


def test_get_agent_checkins_agent_not_found(client, admin_auth_header):
    response = client.get("/api/v2/agents/XYZ123/checkins", headers=admin_auth_header)

    assert response.status_code == 404
    assert response.json()["detail"] == "Agent not found for id XYZ123"


def test_get_agent_checkins_with_limit_and_page(
    client, admin_auth_header, agent, session_local, models
):
    asyncio.run(_create_checkins(session_local, models, [agent]))

    response = client.get(
        f"/api/v2/agents/{agent}/checkins?limit=10&page=1", headers=admin_auth_header
    )

    assert response.status_code == 200
    assert len(response.json()["records"]) == 10
    assert response.json()["total"] > days_back * 17280
    assert response.json()["page"] == 1

    page1 = response.json()["records"]

    response = client.get(
        f"/api/v2/agents/{agent}/checkins?limit=10&page=2", headers=admin_auth_header
    )

    assert response.status_code == 200
    assert len(response.json()["records"]) == 10
    assert response.json()["total"] > days_back * 17280
    assert response.json()["page"] == 2

    page2 = response.json()["records"]

    assert page1 != page2


@pytest.mark.slow
def test_get_agent_checkins_multiple_agents(
    client, admin_auth_header, agents, session_local, models
):
    with_checkins = agents[:3]
    asyncio.run(_create_checkins(session_local, models, with_checkins))

    response = client.get(
        "/api/v2/agents/checkins",
        headers=admin_auth_header,
        params={"agents": with_checkins[:2], "limit": 400000},
    )

    assert response.status_code == 200
    assert len(response.json()["records"]) == days_back * 17280 * 2
    assert set([r["agent_id"] for r in response.json()["records"]]) == set(
        with_checkins[:2]
    )


@pytest.mark.slow
def test_agent_checkins_aggregate(
    client, admin_auth_header, session_local, models, agents, empire_config
):
    if empire_config.database.use == "sqlite":
        pytest.skip("sqlite not supported for checkin aggregation")

    asyncio.run(_create_checkins(session_local, models, agents[:3]))

    response = client.get(
        "/api/v2/agents/checkins/aggregate",
        headers=admin_auth_header,
    )

    assert response.status_code == 200
    assert response.elapsed.total_seconds() < 2
    assert response.json()["bucket_size"] == "day"
    assert response.json()["records"][1]["count"] == 17280 * 3

    response = client.get(
        "/api/v2/agents/checkins/aggregate",
        headers=admin_auth_header,
        params={"bucket_size": "hour"},
    )

    assert response.status_code == 200
    assert response.elapsed.total_seconds() < 2
    assert response.json()["bucket_size"] == "hour"
    assert response.json()["records"][1]["count"] == 720 * 3

    response = client.get(
        "/api/v2/agents/checkins/aggregate",
        headers=admin_auth_header,
        params={"bucket_size": "minute"},
    )

    assert response.status_code == 200
    assert response.elapsed.total_seconds() < 2
    assert response.json()["bucket_size"] == "minute"
    assert response.json()["records"][1]["count"] == 12 * 3

    response = client.get(
        "/api/v2/agents/checkins/aggregate",
        headers=admin_auth_header,
        params={"bucket_size": "second"},
    )

    assert response.status_code == 200
    # On an m1 macbook this is <1s, but in CI it's ~11s. ymmv
    # Changed from 15 to 17 in 2023/07
    assert response.elapsed.total_seconds() < 17
    assert response.json()["bucket_size"] == "second"
    assert response.json()["records"][1]["count"] == 1 * 3

    # Test start date and end date
    response = client.get(
        "/api/v2/agents/checkins/aggregate",
        headers=admin_auth_header,
        params={"bucket_size": "hour", "start_date": start_time + timedelta(days=3)},
    )

    assert response.status_code == 200
    assert response.json()["bucket_size"] == "hour"
    checkin_time_string = response.json()["records"][0]["checkin_time"]
    checkin_time = datetime.strptime(checkin_time_string, "%Y-%m-%dT%H:%M:%S%z")
    assert checkin_time == start_time + timedelta(days=3)

    response = client.get(
        "/api/v2/agents/checkins/aggregate",
        headers=admin_auth_header,
        params={"bucket_size": "hour", "end_date": start_time + timedelta(days=3)},
    )

    assert response.status_code == 200
    assert response.json()["bucket_size"] == "hour"
    checkin_time_string = response.json()["records"][-1]["checkin_time"]
    checkin_time = datetime.strptime(checkin_time_string, "%Y-%m-%dT%H:%M:%S%z")
    assert checkin_time == start_time + timedelta(days=3)

    # Test using timestamps with offset
    with_tz = start_time + timedelta(days=3)
    with_tz = with_tz.astimezone(timezone(timedelta(hours=-5)))

    response = client.get(
        "/api/v2/agents/checkins/aggregate",
        headers=admin_auth_header,
        params={"bucket_size": "hour", "start_date": with_tz},
    )

    assert response.status_code == 200
    assert response.json()["bucket_size"] == "hour"
    checkin_time_string = response.json()["records"][0]["checkin_time"]
    checkin_time = datetime.strptime(checkin_time_string, "%Y-%m-%dT%H:%M:%S%z")
    assert checkin_time == start_time + timedelta(days=3)
