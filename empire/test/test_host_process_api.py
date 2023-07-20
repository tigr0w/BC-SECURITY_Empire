import pytest


@pytest.fixture(scope="function", autouse=True)
def processes(db, host, agent, models):
    db_agent = db.query(models.Agent).filter(models.Agent.session_id == agent).first()
    db_agent.process_id = "11"
    process1 = models.HostProcess(
        host_id=host,
        process_id=db_agent.process_id,
        process_name="explorer.exe",
        architecture="x86",
        user="CX01N",
    )

    process2 = models.HostProcess(
        host_id=host,
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


def test_get_process_host_not_found(client, admin_auth_header):
    response = client.get("/api/v2/hosts/9999/processes", headers=admin_auth_header)

    assert response.status_code == 404
    assert response.json()["detail"] == "Host not found for id 9999"


def test_get_process_not_found(client, admin_auth_header, host):
    response = client.get(
        f"/api/v2/hosts/{host}/processes/8888", headers=admin_auth_header
    )

    assert response.status_code == 404
    assert (
        response.json()["detail"]
        == f"Process not found for host id {host} and process id 8888"
    )


def test_get_process(client, admin_auth_header, host, processes):
    response = client.get(
        f"/api/v2/hosts/{host}/processes/{processes[0].process_id}",
        headers=admin_auth_header,
    )

    assert response.status_code == 200
    assert response.json()["process_id"] == processes[0].process_id
    assert response.json()["process_name"] == processes[0].process_name
    assert response.json()["host_id"] == processes[0].host_id


def test_get_processes(client, admin_auth_header, host):
    response = client.get(f"/api/v2/hosts/{host}/processes/", headers=admin_auth_header)

    assert response.status_code == 200
    assert len(response.json()["records"]) > 0


def test_agent_join(client, admin_auth_header, host, agent):
    response = client.get(f"/api/v2/hosts/{host}/processes/", headers=admin_auth_header)

    assert response.status_code == 200
    assert (
        len(
            list(
                filter(
                    lambda x: x["agent_id"] == agent,
                    response.json()["records"],
                )
            )
        )
        == 1
    )
