import os


def test_agent_logging(client, admin_auth_header, agent, empire_config):
    """
    Test that the agent logs to the agent log file.
    This is super basic and could be expanded later to test responses.
    """
    response = client.post(
        f"/api/v2/agents/{agent}/tasks/shell",
        headers=admin_auth_header,
        json={
            "command": 'echo "Hello World!"',
        },
    )

    assert response.status_code == 201

    agent_log_file = os.path.join(
        empire_config.yaml["directories"]["downloads"], agent, "agent.log"
    )

    assert os.path.exists(agent_log_file)
    with open(agent_log_file) as f:
        assert f"Tasked {agent} to run TASK_SHELL" in f.read()
