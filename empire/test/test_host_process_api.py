import pytest

from empire.server.database import models


@pytest.fixture(scope="module", autouse=True)
def hosts(db):
    hosts = db.query(models.Host).all()

    if not hosts:
        host = models.Host(name="HOST_1", internal_ip="1.1.1.1")

        host2 = models.Host(name="HOST_2", internal_ip="2.2.2.2")
        db.add(host)
        db.add(host2)
        db.flush()
        db.commit()

        hosts = [host, host2]

    yield hosts

    db.delete(hosts[0])
    db.delete(hosts[1])
    db.commit()


@pytest.fixture(scope="module", autouse=True)
def processes(db, hosts):
    processes = db.query(models.HostProcess).all()

    if not processes:
        process1 = models.HostProcess(
            host_id=hosts[0].id,
            process_id="11",
            process_name="explorer.exe",
            architecture="x86",
            user="CX01N",
        )

        process2 = models.HostProcess(
            host_id=hosts[0].id,
            process_id="12",
            process_name="discord.exe",
            architecture="x86",
            user="Admin",
        )
        db.add(process1)
        db.add(process2)
        db.flush()
        db.commit()

        processes = [process1, process2]

    yield processes

    db.delete(processes[0])
    db.delete(processes[1])
    db.commit()


@pytest.fixture(scope="module", autouse=True)
def agent(db, processes):
    agent = db.query(models.Agent).first()

    if not agent:
        agent = models.Agent(
            name="TEST123",
            session_id="TEST123",
            host_id=processes[0].host_id,
            process_id=processes[0].process_id,
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
            archived=False,
        )
        db.add(agent)
        db.flush()
        db.commit()

    yield agent

    db.delete(agent)
    db.commit()


def test_get_process_host_not_found(client, admin_auth_header):
    response = client.get("/api/v2beta/hosts/9999/processes", headers=admin_auth_header)

    assert response.status_code == 404
    assert response.json()["detail"] == "Host not found for id 9999"


def test_get_process_not_found(client, admin_auth_header, hosts):
    response = client.get(
        f"/api/v2beta/hosts/{hosts[0].id}/processes/8888", headers=admin_auth_header
    )

    assert response.status_code == 404
    assert (
        response.json()["detail"]
        == f"Process not found for host id {hosts[0].id} and process id 8888"
    )


def test_get_process(client, admin_auth_header, hosts, processes):
    response = client.get(
        f"/api/v2beta/hosts/{hosts[0].id}/processes/{processes[0].process_id}",
        headers=admin_auth_header,
    )

    assert response.status_code == 200
    assert response.json()["process_id"] == processes[0].process_id
    assert response.json()["process_name"] == processes[0].process_name
    assert response.json()["host_id"] == processes[0].host_id


def test_get_processes(client, admin_auth_header, hosts):
    response = client.get(
        f"/api/v2beta/hosts/{hosts[0].id}/processes/", headers=admin_auth_header
    )

    assert response.status_code == 200
    assert len(response.json()["records"]) > 0


def test_agent_join(client, admin_auth_header, hosts, agent):
    response = client.get(
        f"/api/v2beta/hosts/{hosts[0].id}/processes/", headers=admin_auth_header
    )

    assert response.status_code == 200
    assert (
        len(
            list(
                filter(
                    lambda x: x["agent"] == agent.session_id, response.json()["records"]
                )
            )
        )
        == 1
    )
