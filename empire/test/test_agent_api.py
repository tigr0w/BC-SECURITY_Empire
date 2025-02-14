from starlette import status

from empire.server.common.empire import MainMenu


def test_get_agent_not_found(client, admin_auth_header):
    response = client.get("/api/v2/agents/XYZ123", headers=admin_auth_header)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Agent not found for id XYZ123"


def test_get_agent(client, admin_auth_header):
    expected_delay = 60
    expected_jitter = 0.1
    response = client.get("/api/v2/agents/TEST123", headers=admin_auth_header)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["session_id"] == "TEST123"
    assert response.json()["delay"] == expected_delay
    assert response.json()["jitter"] == expected_jitter


def test_get_agents(client, admin_auth_header):
    expected_agents = 3
    response = client.get("/api/v2/agents", headers=admin_auth_header)

    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()["records"]) == expected_agents


def test_get_agents_include_stale_false(client, admin_auth_header):
    expected_agents = 2
    response = client.get(
        "/api/v2/agents?include_stale=false", headers=admin_auth_header
    )

    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()["records"]) == expected_agents


def test_get_agents_include_archived_true(client, admin_auth_header):
    expected_agents = 4
    response = client.get(
        "/api/v2/agents?include_archived=true", headers=admin_auth_header
    )

    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()["records"]) == expected_agents


def test_update_agent_not_found(client, admin_auth_header):
    response = client.get("/api/v2/agents/TEST123", headers=admin_auth_header)
    agent = response.json()

    response = client.put(
        "/api/v2/agents/XYZ123", json=agent, headers=admin_auth_header
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Agent not found for id XYZ123"


def test_update_agent_name_conflict(client, admin_auth_header):
    response = client.get("/api/v2/agents/TEST123", headers=admin_auth_header)
    agent = response.json()
    agent["name"] = "SECOND"

    response = client.put(
        "/api/v2/agents/TEST123", json=agent, headers=admin_auth_header
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "Agent with name SECOND already exists."


def test_update_agent(client, admin_auth_header):
    response = client.get("/api/v2/agents/TEST123", headers=admin_auth_header)

    agent = response.json()
    agent["name"] = "My New Agent Name"
    agent["notes"] = "The new notes!"
    response = client.put(
        "/api/v2/agents/TEST123", json=agent, headers=admin_auth_header
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["name"] == "My New Agent Name"
    assert response.json()["notes"] == "The new notes!"


def test_create_agent(main: MainMenu, session_local):
    with session_local() as db:
        agent = main.agentsv2.create_agent(
            db,
            "ABC123",
            "1.1.1.1",
            60,
            0.1,
            "Windows",
            None,
            None,
            None,
            "SESSION_KEY",
            "",
            "http",
            "powershell",
        )

        assert agent is not None
