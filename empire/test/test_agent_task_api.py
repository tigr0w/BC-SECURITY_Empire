from textwrap import dedent

import pytest

from empire.test.conftest import base_listener_non_fixture


@pytest.fixture(scope="module", autouse=True)
def listener(client, admin_auth_header):
    # not using fixture because scope issues
    response = client.post(
        "/api/v2/listeners/",
        headers=admin_auth_header,
        json=base_listener_non_fixture(),
    )

    yield response.json()

    client.delete(
        f"/api/v2/listeners/{response.json()['id']}", headers=admin_auth_header
    )


@pytest.fixture(scope="module", autouse=True)
def agent_low_version(db, models, main):
    agent = db.query(models.Agent).filter(models.Agent.session_id == "WEAK").first()
    if not agent:
        agent = models.Agent(
            name="WEAK",
            session_id="WEAK",
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
            language_version="1",
            high_integrity=True,
            archived=False,
        )
        db.add(agent)
        db.flush()
        db.commit()

    main.agents.agents["WEAK"] = {
        "sessionKey": agent.session_key,
        "functions": agent.functions,
    }

    yield agent

    db.query(models.AgentTask).filter(
        models.AgentTask.agent_id == agent.session_id
    ).delete()
    db.delete(agent)
    db.commit()


@pytest.fixture(scope="module", autouse=True)
def agent_archived(db, models, main):
    agent = db.query(models.Agent).filter(models.Agent.session_id == "WEAK").first()
    if not agent:
        agent = models.Agent(
            name="iamarchived",
            session_id="iamarchived",
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
            language_version="1",
            high_integrity=True,
            archived=True,
        )
        db.add(agent)
        db.flush()
        db.commit()

    main.agents.agents["iamarchived"] = {
        "sessionKey": agent.session_key,
        "functions": agent.functions,
    }

    yield agent

    db.delete(agent)
    db.commit()


@pytest.fixture(scope="module", autouse=True)
def agent_low_integrity(db, models, main):
    agent = db.query(models.Agent).filter(models.Agent.session_id == "WEAK2").first()
    if not agent:
        agent = models.Agent(
            name="WEAK2",
            session_id="WEAK2",
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
            archived=False,
        )
        db.add(agent)
        db.flush()
        db.commit()

    main.agents.agents["WEAK2"] = {
        "sessionKey": agent.session_key,
        "functions": agent.functions,
    }

    yield agent

    db.query(models.AgentTask).filter(
        models.AgentTask.agent_id == agent.session_id
    ).delete()
    db.delete(agent)
    db.commit()


@pytest.fixture(scope="module", autouse=True)
def download(client, admin_auth_header, db, models):
    response = client.post(
        "/api/v2/downloads",
        headers=admin_auth_header,
        files={
            "file": (
                "test-upload.yaml",
                open("./empire/test/test-upload.yaml", "r").read(),
            )
        },
    )

    yield response.json()

    # there is no delete endpoint for downloads, so we need to delete the file manually
    try:
        db.query(models.Download).delete()
    except Exception:
        pass


@pytest.fixture(scope="module", autouse=True)
def bof_download(client, admin_auth_header, db, models):
    response = client.post(
        "/api/v2/downloads",
        headers=admin_auth_header,
        files={
            "file": (
                "whoami.x64.o",
                open("./empire/test/data/whoami.x64.o", "rb").read(),
            )
        },
    )

    yield response.json()

    # there is no delete endpoint for downloads, so we need to delete the file manually
    try:
        db.query(models.Download).delete()
    except Exception:
        pass


@pytest.fixture(scope="function")
def agent_task(client, admin_auth_header, agent):
    resp = client.post(
        f"/api/v2/agents/{agent}/tasks/shell",
        headers=admin_auth_header,
        json={"command": 'echo "HELLO WORLD"'},
    )

    yield resp.json()

    # No need to delete the task, it will be deleted when the agent is deleted
    # After the test.


def test_create_task_shell_agent_not_found(client, admin_auth_header):
    response = client.post(
        "/api/v2/agents/abc/tasks/shell",
        headers=admin_auth_header,
        json={"command": 'echo "HELLO WORLD"'},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Agent not found for id abc"


def test_create_task_shell(client, admin_auth_header, agent):
    response = client.post(
        f"/api/v2/agents/{agent}/tasks/shell",
        headers=admin_auth_header,
        json={"command": 'echo "HELLO WORLD"'},
    )
    assert response.status_code == 201
    assert response.json()["input"] == 'echo "HELLO WORLD"'
    assert response.json()["id"] > 0


def test_create_task_module_agent_not_found(client, admin_auth_header):
    response = client.post(
        "/api/v2/agents/abc/tasks/module",
        headers=admin_auth_header,
        json={"module_id": "some_module", "options": {}},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Agent not found for id abc"


def test_create_task_module_not_found(client, admin_auth_header, agent):
    response = client.post(
        f"/api/v2/agents/{agent}/tasks/module",
        headers=admin_auth_header,
        json={"module_id": "some_module", "options": {}},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Module not found for id some_module"


def test_create_task_module(client, admin_auth_header, agent):
    response = client.post(
        f"/api/v2/agents/{agent}/tasks/module",
        headers=admin_auth_header,
        json={
            "module_id": "powershell_credentials_invoke_internal_monologue",
            "options": {
                "Challenge": "1122334455667788",
                "Downgrade": "",
                "Impersonate": "",
                "Restore": "",
                # "Verbose": "",
            },
        },
    )

    assert response.status_code == 201
    assert response.json()["id"] > 0
    assert response.json()["input"].startswith("function Invoke-InternalMonologue")
    assert response.json()["agent_id"] == agent


def test_create_task_module_modified_input(client, admin_auth_header, agent):
    modified_input = dedent(
        """
                function Invoke-InternalMonologue {
                    This is a modified input
                }
            """
    ).lstrip("\n")

    response = client.post(
        f"/api/v2/agents/{agent}/tasks/module",
        headers=admin_auth_header,
        json={
            "module_id": "powershell_credentials_invoke_internal_monologue",
            "options": {
                "Challenge": "1122334455667788",
                "Downgrade": "",
                "Impersonate": "",
                "Restore": "",
            },
            "modified_input": modified_input,
        },
    )

    assert response.status_code == 201
    assert response.json()["id"] > 0
    assert response.json()["input"].startswith(modified_input)
    assert response.json()["agent_id"] == agent


def test_create_task_bof_module_disabled_csharpserver(
    client, admin_auth_header, agent, bof_download
):
    response = client.post(
        f"/api/v2/agents/{agent}/tasks/module",
        headers=admin_auth_header,
        json={
            "module_id": "csharp_inject_bof_inject_bof",
            "options": {
                "File": bof_download["id"],
                "EntryPoint": "",
                "ArgumentList": "",
                "Architecture": "x64",
            },
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "csharpserver plugin not running"


def test_create_task_module_with_file_option_not_found(
    client, admin_auth_header, agent, bof_download
):
    response = client.post(
        f"/api/v2/agents/{agent}/tasks/module",
        headers=admin_auth_header,
        json={
            "module_id": "powershell_code_execution_invoke_shellcode",
            "options": {
                "File": "999",
            },
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "File not found for 'File' id 999"


def test_create_task_module_with_file_option(
    client, admin_auth_header, agent, bof_download
):
    response = client.post(
        f"/api/v2/agents/{agent}/tasks/module",
        headers=admin_auth_header,
        json={
            "module_id": "powershell_code_execution_invoke_shellcode",
            "options": {
                "File": bof_download["id"],
            },
        },
    )

    assert response.status_code == 201
    assert response.json()["id"] > 0


def test_create_task_module_validates_required_options(
    client, admin_auth_header, agent
):
    response = client.post(
        f"/api/v2/agents/{agent}/tasks/module",
        headers=admin_auth_header,
        json={
            "module_id": "powershell_trollsploit_message",
            "options": {
                "MsgText": "",
                "IconType": "Critical",
                "Title": "ERROR - 0xA801B720",
            },
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "required option missing: MsgText"


def test_create_task_module_validates_options_strict(client, admin_auth_header, agent):
    response = client.post(
        f"/api/v2/agents/{agent}/tasks/module",
        headers=admin_auth_header,
        json={
            "module_id": "powershell_collection_foxdump",
            "options": {
                "OutputFunction": "not-valid-choice",
            },
        },
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "OutputFunction must be set to one of the suggested values."
    )


def test_create_task_module_language_version_check(
    client, admin_auth_header, agent_low_version
):
    response = client.post(
        f"/api/v2/agents/{agent_low_version.session_id}/tasks/module",
        headers=admin_auth_header,
        json={
            "module_id": "powershell_trollsploit_message",
            "options": {
                "MsgText": "TestTestTest",
                "IconType": "Critical",
                "Title": "ERROR - 0xA801B720",
            },
        },
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "module requires language version 2 but agent running language version 1"
    )


def test_create_task_module_ignore_language_version_check(
    client, admin_auth_header, agent_low_version
):
    response = client.post(
        f"/api/v2/agents/{agent_low_version.session_id}/tasks/module",
        headers=admin_auth_header,
        json={
            "module_id": "powershell_trollsploit_message",
            "ignore_language_version_check": True,
            "options": {
                "MsgText": "TestTestTest",
                "IconType": "Critical",
                "Title": "ERROR - 0xA801B720",
            },
        },
    )

    assert response.status_code == 201
    assert response.json()["id"] > 0


def test_create_task_module_admin_check(client, admin_auth_header, agent_low_integrity):
    response = client.post(
        f"/api/v2/agents/{agent_low_integrity.session_id}/tasks/module",
        headers=admin_auth_header,
        json={
            "module_id": "powershell_credentials_mimikatz_logonpasswords",
            "options": {},
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "module needs to run in an elevated context"


def test_create_task_module_ignore_admin_check(
    client, admin_auth_header, agent_low_integrity
):
    response = client.post(
        f"/api/v2/agents/{agent_low_integrity.session_id}/tasks/module",
        headers=admin_auth_header,
        json={
            "module_id": "powershell_credentials_mimikatz_logonpasswords",
            "ignore_admin_check": True,
            "options": {},
        },
    )

    assert response.status_code == 201
    assert response.json()["id"] > 0


def test_create_task_upload_file_not_found(client, admin_auth_header, agent):
    response = client.post(
        f"/api/v2/agents/{agent}/tasks/upload",
        headers=admin_auth_header,
        json={
            "path_to_file": "/tmp",
            "file_id": 9999,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Download not found for id 9999"


def test_create_task_upload_agent_not_found(client, admin_auth_header, agent):
    response = client.post(
        "/api/v2/agents/abc/tasks/upload",
        headers=admin_auth_header,
        json={
            "path_to_file": "/tmp",
            "file_id": 1,
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Agent not found for id abc"


def test_create_task_upload(client, admin_auth_header, agent, download):
    response = client.post(
        f"/api/v2/agents/{agent}/tasks/upload",
        headers=admin_auth_header,
        json={
            "path_to_file": "/tmp",
            "file_id": download["id"],
        },
    )

    assert response.status_code == 201
    assert response.json()["id"] > 0
    assert response.json()["input"].startswith("/tmp")


def test_create_task_download_agent_not_found(client, admin_auth_header):
    response = client.post(
        "/api/v2/agents/abc/tasks/download",
        headers=admin_auth_header,
        json={"path_to_file": "/tmp/downloadme.zip"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Agent not found for id abc"


def test_create_task_download(client, admin_auth_header, agent):
    response = client.post(
        f"/api/v2/agents/{agent}/tasks/download",
        headers=admin_auth_header,
        json={"path_to_file": "/tmp/downloadme.zip"},
    )

    assert response.status_code == 201
    assert response.json()["id"] > 0


def test_create_socks_agent_not_found(client, admin_auth_header, agent):
    response = client.post(
        "/api/v2/agents/abc/tasks/socks",
        headers=admin_auth_header,
        json={},
    )

    assert response.status_code == 404


def test_create_task_socks(client, admin_auth_header, agent):
    response = client.post(
        f"/api/v2/agents/{agent}/tasks/socks",
        headers=admin_auth_header,
        json={"port": 1080},
    )

    assert response.status_code == 201
    assert response.json()["id"] > 0


def test_create_task_jobs_agent_not_found(client, admin_auth_header, agent):
    response = client.post(
        "/api/v2/agents/abc/tasks/jobs",
        headers=admin_auth_header,
        json={},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Agent not found for id abc"


def test_create_task_jobs(client, admin_auth_header, agent):
    response = client.post(
        f"/api/v2/agents/{agent}/tasks/jobs",
        headers=admin_auth_header,
        json={},
    )

    assert response.status_code == 200


def test_kill_task_jobs(client, admin_auth_header, agent):
    response = client.post(
        f"/api/v2/agents/{agent}/tasks/kill_job",
        headers=admin_auth_header,
        json={"id": 0},
    )

    assert response.status_code == 200


def test_kill_task_jobs_agent_not_found(client, admin_auth_header, agent):
    response = client.post(
        "/api/v2/agents/abc/tasks/kill_job",
        headers=admin_auth_header,
        json={"id": 0},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Agent not found for id abc"


def test_create_task_script_import_agent_not_found(client, admin_auth_header, agent):
    response = client.post(
        "/api/v2/agents/abc/tasks/script_import",
        headers=admin_auth_header,
        files={
            "file": (
                "test-upload.yaml",
                open("./empire/test/test-upload.yaml", "r"),
                "text/plain",
            )
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Agent not found for id abc"


def test_create_task_script_import(client, admin_auth_header, agent):
    response = client.post(
        f"/api/v2/agents/{agent}/tasks/script_import",
        headers=admin_auth_header,
        files={
            "file": (
                "test-upload.yaml",
                open("./empire/test/test-upload.yaml", "r"),
                "text/plain",
            )
        },
    )

    assert response.status_code == 201
    assert response.json()["id"] > 0


def test_create_task_script_command_agent_not_found(client, admin_auth_header):
    response = client.post(
        "/api/v2/agents/abc/tasks/script_command",
        headers=admin_auth_header,
        json={"command": "run command"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Agent not found for id abc"


def test_create_task_script_command(client, admin_auth_header, agent):
    response = client.post(
        f"/api/v2/agents/{agent}/tasks/script_command",
        headers=admin_auth_header,
        json={"command": "run command"},
    )

    assert response.status_code == 201
    assert response.json()["id"] > 0
    assert response.json()["input"] == "run command"


def test_create_task_sysinfo_agent_not_found(client, admin_auth_header):
    response = client.post(
        "/api/v2/agents/abc/tasks/sysinfo", headers=admin_auth_header
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Agent not found for id abc"


def test_create_task_sysinfo(client, admin_auth_header, agent):
    response = client.post(
        f"/api/v2/agents/{agent}/tasks/sysinfo",
        headers=admin_auth_header,
        json={},
    )

    assert response.status_code == 201
    assert response.json()["id"] > 0


def test_create_task_update_comms_agent_not_found(client, admin_auth_header, listener):
    response = client.post(
        "/api/v2/agents/abc/tasks/update_comms",
        headers=admin_auth_header,
        json={"new_listener_id": listener["id"]},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Agent not found for id abc"


def test_create_task_update_comms(client, admin_auth_header, agent, listener):
    response = client.post(
        f"/api/v2/agents/{agent}/tasks/update_comms",
        headers=admin_auth_header,
        json={"new_listener_id": listener["id"]},
    )

    assert response.status_code == 201
    assert response.json()["id"] > 0


def test_create_task_update_sleep_agent_not_found(client, admin_auth_header, listener):
    response = client.post(
        "/api/v2/agents/abc/tasks/sleep",
        headers=admin_auth_header,
        json={"new_listener_id": listener["id"]},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Agent not found for id abc"


def test_create_task_update_sleep_validates_fields(client, admin_auth_header, agent):
    response = client.post(
        f"/api/v2/agents/{agent}/tasks/sleep",
        headers=admin_auth_header,
        json={"delay": -1, "jitter": 5},
    )

    assert response.status_code == 422

    delay_err = list(filter(lambda x: "delay" in x["loc"], response.json()["detail"]))[
        0
    ]
    jitter_err = list(
        filter(lambda x: "jitter" in x["loc"], response.json()["detail"])
    )[0]
    assert delay_err["loc"] == ["body", "delay"]
    assert delay_err["msg"] == "ensure this value is greater than or equal to 0"
    assert jitter_err["loc"] == ["body", "jitter"]
    assert jitter_err["msg"] == "ensure this value is less than or equal to 1"


def test_create_task_update_sleep(client, admin_auth_header, agent):
    response = client.post(
        f"/api/v2/agents/{agent}/tasks/sleep",
        headers=admin_auth_header,
        json={"delay": 30, "jitter": 0.5},
    )

    assert response.status_code == 201
    assert response.json()["id"] > 0


def test_create_task_update_kill_date_agent_not_found(client, admin_auth_header):
    response = client.post(
        "/api/v2/agents/abc/tasks/kill_date",
        headers=admin_auth_header,
        json={"kill_date": "2021-05-06T00:00Z"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Agent not found for id abc"


def test_create_task_update_kill_date(client, admin_auth_header, agent):
    response = client.post(
        f"/api/v2/agents/{agent}/tasks/kill_date",
        headers=admin_auth_header,
        json={"kill_date": "2021-05-06T00:00Z"},
    )

    assert response.status_code == 201
    assert response.json()["id"] > 0


def test_create_task_update_working_hours_agent_not_found(client, admin_auth_header):
    response = client.post(
        "/api/v2/agents/abc/tasks/working_hours",
        headers=admin_auth_header,
        json={"working_hours": "05:00-12:00"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Agent not found for id abc"


def test_create_task_update_working_hours(client, admin_auth_header, agent):
    response = client.post(
        f"/api/v2/agents/{agent}/tasks/working_hours",
        headers=admin_auth_header,
        json={"working_hours": "05:00-12:00"},
    )

    assert response.status_code == 201
    assert response.json()["id"] > 0


def test_create_task_directory_list_agent_not_found(client, admin_auth_header):
    response = client.post(
        "/api/v2/agents/abc/tasks/directory_list",
        headers=admin_auth_header,
        json={"path": "/"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Agent not found for id abc"


def test_create_task_directory_list(client, admin_auth_header, agent):
    response = client.post(
        f"/api/v2/agents/{agent}/tasks/directory_list",
        headers=admin_auth_header,
        json={"path": "/"},
    )

    assert response.status_code == 201
    assert response.json()["id"] > 0


def test_create_task_proxy_list(client, admin_auth_header, agent):
    proxy_body = {
        "proxies": [
            {
                "proxy_type": "HTTP",
                "host": "proxy.com",
                "port": 8080,
            },
            {
                "proxy_type": "SOCKS5",
                "host": "proxy2.com",
                "port": 8081,
            },
        ]
    }

    response = client.post(
        f"/api/v2/agents/{agent}/tasks/proxy_list",
        headers=admin_auth_header,
        json=proxy_body,
    )

    assert response.status_code == 201
    assert response.json()["id"] > 0

    response = client.get(f"/api/v2/agents/{agent}", headers=admin_auth_header)

    assert response.status_code == 200
    assert response.json()["proxies"] == proxy_body


def test_create_task_exit_agent_not_found(client, admin_auth_header):
    response = client.post("/api/v2/agents/abc/tasks/exit", headers=admin_auth_header)

    assert response.status_code == 404
    assert response.json()["detail"] == "Agent not found for id abc"


def test_get_tasks_for_agent_agent_not_found(client, admin_auth_header):
    response = client.get("/api/v2/agents/abc/tasks", headers=admin_auth_header)
    assert response.status_code == 404
    assert response.json()["detail"] == "Agent not found for id abc"


def test_get_tasks_for_agent(client, admin_auth_header, agent, agent_task):
    response = client.get(f"/api/v2/agents/{agent}/tasks", headers=admin_auth_header)
    assert response.status_code == 200
    assert len(response.json()["records"]) > 0
    assert (
        len(
            list(
                filter(
                    lambda x: x["agent_id"] != agent,
                    response.json()["records"],
                )
            )
        )
        == 0
    )


def test_get_task_for_agent_agent_not_found(client, admin_auth_header, agent):
    response = client.get("/api/v2/agents/abc/tasks/1", headers=admin_auth_header)
    assert response.status_code == 404
    assert response.json()["detail"] == "Agent not found for id abc"


def test_get_task_for_agent_not_found(client, admin_auth_header, agent):
    response = client.get(
        f"/api/v2/agents/{agent}/tasks/9999", headers=admin_auth_header
    )
    assert response.status_code == 404
    assert (
        response.json()["detail"]
        == f"Task not found for agent {agent} and task id 9999"
    )


def test_get_task_for_agent(client, admin_auth_header, agent, agent_task):
    response = client.get(f"/api/v2/agents/{agent}/tasks/1", headers=admin_auth_header)
    assert response.status_code == 200
    assert response.json()["id"] == 1
    assert response.json()["agent_id"] == agent


def test_create_task_archived_agent(client, admin_auth_header, agent_archived):
    response = client.post(
        f"/api/v2/agents/{agent_archived.session_id}/tasks/shell",
        headers=admin_auth_header,
        json={"command": 'echo "HELLO WORLD"'},
    )
    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == f"[!] Agent {agent_archived.session_id} is archived."
    )


def test_delete_task(client, admin_auth_header, agent, agent_task):
    response = client.delete(
        f"/api/v2/agents/{agent}/tasks/1", headers=admin_auth_header
    )

    assert response.status_code == 204


def test_last_task(client, admin_auth_header, agent, empire_config):
    response = client.post(
        f"/api/v2/agents/{agent}/tasks/shell",
        headers=admin_auth_header,
        json={"command": 'echo "HELLO WORLD"'},
    )

    assert response.status_code == 201

    location = empire_config.yaml["debug"]["last_task"]["file"]
    with open(location, "r") as f:
        last_task = f.read()

    assert 'echo "HELLO WORLD"' in last_task


def test_create_task_exit(client, admin_auth_header, agent):
    """
    This is at the end so it doesn't interfere with other tests
    """
    response = client.post(
        f"/api/v2/agents/{agent}/tasks/exit",
        headers=admin_auth_header,
        json={},
    )

    assert response.status_code == 201
    assert response.json()["id"] > 0
