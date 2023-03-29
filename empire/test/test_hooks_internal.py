import json

import pytest

from empire.server.core.db.models import AgentTaskStatus
from empire.server.core.hooks import hooks


@pytest.fixture(scope="module", autouse=True)
def agent(db, models, main):
    hosts = db.query(models.Host).all()
    if len(hosts) == 0:
        host = models.Host(name="default_host", internal_ip="127.0.0.1")
        db.add(host)
    else:
        host = hosts[0]

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
            hostname=host.name,
            host_id=host.id,
            archived=False,
        )
        db.add(agent)
    else:
        agent.archived = False

    db.flush()

    main.agents.agents[name] = {
        "sessionKey": agent.session_key,
        "functions": agent.functions,
    }

    yield agent

    db.query(models.HostProcess).delete()
    db.delete(agent)
    db.delete(host)
    db.commit()


def test_ps_hook(client, db, models, agent):
    existing_processes = [
        models.HostProcess(
            host_id=agent.host_id,
            process_id=1,
            process_name="should_be_stale",
            architecture="x86",
            user="test_user",
        ),
        models.HostProcess(
            host_id=agent.host_id,
            process_id=2,
            process_name="should_be_updated",
            architecture="x86",
            user="test_user",
        ),
        models.HostProcess(
            host_id=agent.host_id,
            process_id=3,
            process_name="should_be_same",
            architecture="x86",
            user="test_user",
        ),
    ]
    db.add_all(existing_processes)

    output = json.dumps(
        [
            {
                "CMD": "has_been_updated",
                "PID": 2,
                "Arch": "x86_64",
                "UserName": "test_user",
            },
            {"CMD": "should_be_same", "PID": 3, "Arch": "x86", "UserName": "test_user"},
            {"CMD": "should_be_new", "PID": 4, "Arch": "x86", "UserName": "test_user"},
        ]
    )
    task = models.AgentTask(
        id=1,
        agent_id=agent.session_id,
        agent=agent,
        input="ps",
        status=AgentTaskStatus.pulled,
        output=output,
        original_output=output,
    )
    hooks.run_hooks(hooks.BEFORE_TASKING_RESULT_HOOK, db, task)
    db.flush()
    processes = db.query(models.HostProcess).all()

    assert len(processes) == 4
    assert processes[0].process_name == "should_be_stale"
    assert processes[0].stale is True
    assert processes[1].process_name == "has_been_updated"
    assert processes[1].stale is False
    assert processes[2].process_name == "should_be_same"
    assert processes[2].stale is False
    assert processes[3].process_name == "should_be_new"
    assert processes[3].stale is False
