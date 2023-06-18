from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture(scope="module", autouse=True)
def agent(db, models, main):
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
            name="ARCHIVED",
            session_id="ARCHIVED",
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
        db.commit()
        agents = [agent, agent2, agent3, agent4]

    main.agents.agents["TEST123"] = {
        "sessionKey": agents[0].session_key,
        "functions": agents[0].functions,
    }
    main.agents.agents["SECOND"] = {
        "sessionKey": agents[1].session_key,
        "functions": agents[1].functions,
    }
    main.agents.agents["ARCHIVED"] = {
        "sessionKey": agents[2].session_key,
        "functions": agents[2].functions,
    }
    main.agents.agents["STALE"] = {
        "sessionKey": agents[3].session_key,
        "functions": agents[3].functions,
    }

    yield agents

    db.delete(agents[0])
    db.delete(agents[1])
    db.delete(agents[2])
    db.delete(agents[3])
    db.delete(host)
    db.commit()


def test_get_agent_not_found(client, admin_auth_header):
    response = client.get("/api/v2/agents/XYZ123", headers=admin_auth_header)

    assert response.status_code == 404
    assert response.json()["detail"] == "Agent not found for id XYZ123"


def test_get_agent(client, admin_auth_header):
    response = client.get("/api/v2/agents/TEST123", headers=admin_auth_header)

    assert response.status_code == 200
    assert response.json()["session_id"] == "TEST123"
    assert response.json()["delay"] == 60
    assert response.json()["jitter"] == 0.1


def test_get_agents(client, admin_auth_header):
    response = client.get("/api/v2/agents", headers=admin_auth_header)

    assert response.status_code == 200
    assert len(response.json()["records"]) == 3


def test_get_agents_include_stale_false(client, admin_auth_header):
    response = client.get(
        "/api/v2/agents?include_stale=false", headers=admin_auth_header
    )

    assert response.status_code == 200
    assert len(response.json()["records"]) == 2


def test_get_agents_include_archived_true(client, admin_auth_header):
    response = client.get(
        "/api/v2/agents?include_archived=true", headers=admin_auth_header
    )

    assert response.status_code == 200
    assert len(response.json()["records"]) == 4


def test_update_agent_not_found(client, admin_auth_header):
    response = client.get("/api/v2/agents/TEST123", headers=admin_auth_header)
    agent = response.json()

    response = client.put(
        "/api/v2/agents/XYZ123", json=agent, headers=admin_auth_header
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Agent not found for id XYZ123"


def test_update_agent_name_conflict(client, admin_auth_header):
    response = client.get("/api/v2/agents/TEST123", headers=admin_auth_header)
    agent = response.json()
    agent["name"] = "SECOND"

    response = client.put(
        "/api/v2/agents/TEST123", json=agent, headers=admin_auth_header
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Agent with name SECOND already exists."


def test_update_agent(client, admin_auth_header):
    response = client.get("/api/v2/agents/TEST123", headers=admin_auth_header)

    agent = response.json()
    agent["name"] = "My New Agent Name"
    agent["notes"] = "The new notes!"
    response = client.put(
        "/api/v2/agents/TEST123", json=agent, headers=admin_auth_header
    )

    assert response.status_code == 200
    assert response.json()["name"] == "My New Agent Name"
    assert response.json()["notes"] == "The new notes!"
