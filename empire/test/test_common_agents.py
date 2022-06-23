import os

import pytest


@pytest.fixture(scope="module", autouse=True)
def agent(db, models, main):
    name = f'agent_{__name__.split(".")[-1]}'

    agent = db.query(models.Agent).filter(models.Agent.session_id == name).first()
    if not agent:
        agent = models.Agent(
            name=name,
            session_id=name,
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
            high_integrity=True,
            process_name="abc",
            process_id=123,
            hostname="doesntmatter",
            host_id="1",
            archived=False,
        )
        db.add(agent)
    else:
        agent.archived = False

    db.flush()
    db.commit()

    main.agents.agents[name] = {
        "sessionKey": agent.session_key,
        "functions": agent.functions,
    }

    yield agent

    db.delete(agent)
    db.commit()


def test_agent_logging(client, admin_auth_header, agent, empire_config):
    """
    Test that the agent logs to the agent log file.
    This is super basic and could be expanded later to test responses.
    """
    response = client.post(
        f"/api/v2/agents/{agent.session_id}/tasks/shell",
        headers=admin_auth_header,
        json={
            "command": 'echo "Hello World!"',
        },
    )

    assert response.status_code == 201

    agent_log_file = os.path.join(
        empire_config.yaml["directories"]["downloads"], agent.session_id, "agent.log"
    )

    assert os.path.exists(agent_log_file)
    with open(agent_log_file, "r") as f:
        assert f"Tasked {agent.session_id} to run TASK_SHELL" in f.read()
