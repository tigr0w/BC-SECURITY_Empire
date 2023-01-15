import pytest


@pytest.fixture(scope="module")
def host(db, models):
    host = models.Host(name="HOST_1", internal_ip="1.1.1.1")

    db.add(host)

    yield host


@pytest.fixture(scope="module", autouse=True)
def agent(client, db, models, main, host):
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

    db.query(models.Tasking).filter(
        models.Tasking.agent_id == agent.session_id
    ).delete()
    db.delete(host)
    db.delete(agent)
    db.commit()


def test_create_task_no_user_id(client, db, agent, main):
    from empire.server.common.empire import MainMenu

    main: MainMenu = main

    resp, err = main.agenttasksv2.create_task_shell(db, agent, "echo 'hi'", True, 0)

    assert err is None
    assert resp.user_id is None
    assert resp.user is None
