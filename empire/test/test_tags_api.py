import pytest

from empire.server.core.db.models import PluginTaskStatus


def _test_add_tag(client, admin_auth_header, path, taggable_id):
    resp = client.post(
        f"{path}/{taggable_id}/tags",
        headers=admin_auth_header,
        json={"name": "test:tag", "value": "test:value"},
    )
    assert resp.status_code == 422
    assert resp.json() == {
        "detail": [
            {
                "ctx": {"pattern": "^[^:]+$"},
                "loc": ["body", "name"],
                "msg": 'string does not match regex "^[^:]+$"',
                "type": "value_error.str.regex",
            },
            {
                "ctx": {"pattern": "^[^:]+$"},
                "loc": ["body", "value"],
                "msg": 'string does not match regex "^[^:]+$"',
                "type": "value_error.str.regex",
            },
        ]
    }

    resp = client.post(
        f"{path}/{taggable_id}/tags",
        headers=admin_auth_header,
        json={"name": "test_tag", "value": "test_value"},
    )

    expected_tag_1 = {
        "name": "test_tag",
        "value": "test_value",
        "color": None,
        "label": "test_tag:test_value",
    }

    assert resp.status_code == 201
    actual_tag_1 = resp.json()
    actual_tag_1.pop("id")
    assert actual_tag_1 == expected_tag_1

    resp = client.get(f"{path}/{taggable_id}", headers=admin_auth_header)
    assert resp.status_code == 200

    actual_tags = resp.json()["tags"]
    assert len(actual_tags) == 1

    actual_tags[0].pop("id")
    assert actual_tags == [expected_tag_1]

    resp = client.post(
        f"{path}/{taggable_id}/tags",
        headers=admin_auth_header,
        json={
            "name": "test_tag",
            "value": "test_value",
            "color": "#0000FF",
        },
    )

    expected_tag_2 = {
        "name": "test_tag",
        "value": "test_value",
        "color": "#0000FF",
        "label": "test_tag:test_value",
    }

    assert resp.status_code == 201
    actual_tag_2 = resp.json()
    actual_tag_2.pop("id")
    assert actual_tag_2 == expected_tag_2

    resp = client.get(f"{path}/{taggable_id}", headers=admin_auth_header)
    assert resp.status_code == 200

    actual_tags = resp.json()["tags"]
    assert len(actual_tags) == 2

    for tag in actual_tags:
        tag.pop("id")

    assert actual_tags == [expected_tag_1, expected_tag_2]

    for tag in resp.json()["tags"]:
        resp = client.delete(
            f"{path}/{taggable_id}/tags/{tag['id']}",
            headers=admin_auth_header,
        )
        assert resp.status_code == 204


def _test_update_tag(client, admin_auth_header, path, taggable_id):
    resp = client.post(
        f"{path}/{taggable_id}/tags",
        headers=admin_auth_header,
        json={"name": "test_tag", "value": "test_value"},
    )

    assert resp.status_code == 201

    expected_tag = {
        "name": "test_tag_updated",
        "value": "test_value_updated",
        "color": "#0000FF",
        "label": "test_tag_updated:test_value_updated",
    }

    resp_bad = client.put(
        f"{path}/{taggable_id}/tags/{resp.json()['id']}",
        headers=admin_auth_header,
        json={"name": "test:tag", "value": "test:value"},
    )
    assert resp_bad.status_code == 422
    assert resp_bad.json() == {
        "detail": [
            {
                "ctx": {"pattern": "^[^:]+$"},
                "loc": ["body", "name"],
                "msg": 'string does not match regex "^[^:]+$"',
                "type": "value_error.str.regex",
            },
            {
                "ctx": {"pattern": "^[^:]+$"},
                "loc": ["body", "value"],
                "msg": 'string does not match regex "^[^:]+$"',
                "type": "value_error.str.regex",
            },
        ]
    }

    resp = client.put(
        f"{path}/{taggable_id}/tags/{resp.json()['id']}",
        headers=admin_auth_header,
        json=expected_tag,
    )

    assert resp.status_code == 200

    actual_tag = resp.json()
    actual_tag.pop("id")
    assert actual_tag == expected_tag

    resp = client.delete(
        f"{path}/{taggable_id}/tags/{resp.json()['id']}",
        headers=admin_auth_header,
    )
    assert resp.status_code == 204


def _test_delete_tag(client, admin_auth_header, path, taggable_id):
    resp = client.post(
        f"{path}/{taggable_id}/tags",
        headers=admin_auth_header,
        json={"name": "test_tag", "value": "test_value"},
    )

    assert resp.status_code == 201

    resp = client.delete(
        f"{path}/{taggable_id}/tags/{resp.json()['id']}",
        headers=admin_auth_header,
    )
    assert resp.status_code == 204

    resp = client.get(f"{path}/{taggable_id}", headers=admin_auth_header)
    assert resp.status_code == 200
    assert resp.json()["tags"] == []


def test_listener_add_tag(client, admin_auth_header, listener):
    _test_add_tag(client, admin_auth_header, "/api/v2/listeners", listener["id"])


def test_agent_add_tag(client, admin_auth_header, agent):
    _test_add_tag(client, admin_auth_header, "/api/v2/agents", agent)


def test_agent_task_add_tag(client, admin_auth_header, agent_task):
    _test_add_tag(
        client,
        admin_auth_header,
        f"/api/v2/agents/{agent_task['agent_id']}/tasks",
        agent_task["id"],
    )


def test_plugin_task_add_tag(client, admin_auth_header, plugin_task):
    _test_add_tag(
        client,
        admin_auth_header,
        "/api/v2/plugins/basic_reporting/tasks",
        plugin_task,
    )


def test_credential_add_tag(client, admin_auth_header, credential):
    _test_add_tag(client, admin_auth_header, "/api/v2/credentials", credential)


def test_download_add_tag(client, admin_auth_header, download):
    _test_add_tag(client, admin_auth_header, "/api/v2/downloads", download)


def test_listener_update_tag(client, admin_auth_header, listener):
    _test_update_tag(client, admin_auth_header, "/api/v2/listeners", listener["id"])


def test_agent_update_tag(client, admin_auth_header, agent):
    _test_update_tag(client, admin_auth_header, "/api/v2/agents", agent)


def test_agent_task_update_tag(client, admin_auth_header, agent_task):
    _test_update_tag(
        client,
        admin_auth_header,
        f"/api/v2/agents/{agent_task['agent_id']}/tasks",
        agent_task["id"],
    )


def test_plugin_task_update_tag(client, admin_auth_header, plugin_task):
    _test_update_tag(
        client,
        admin_auth_header,
        "/api/v2/plugins/basic_reporting/tasks",
        plugin_task,
    )


def test_credential_update_tag(client, admin_auth_header, credential):
    _test_update_tag(client, admin_auth_header, "/api/v2/credentials", credential)


def test_download_update_tag(client, admin_auth_header, download):
    _test_update_tag(client, admin_auth_header, "/api/v2/downloads", download)


def test_listener_delete_tag(client, admin_auth_header, listener):
    _test_delete_tag(client, admin_auth_header, "/api/v2/listeners", listener["id"])


def test_agent_delete_tag(client, admin_auth_header, agent):
    _test_delete_tag(client, admin_auth_header, "/api/v2/agents", agent)


def test_agent_task_delete_tag(client, admin_auth_header, agent_task):
    _test_delete_tag(
        client,
        admin_auth_header,
        f"/api/v2/agents/{agent_task['agent_id']}/tasks",
        agent_task["id"],
    )


def test_plugin_task_delete_tag(client, admin_auth_header, plugin_task):
    _test_delete_tag(
        client,
        admin_auth_header,
        "/api/v2/plugins/basic_reporting/tasks",
        plugin_task,
    )


def test_credential_delete_tag(client, admin_auth_header, credential):
    _test_delete_tag(client, admin_auth_header, "/api/v2/credentials", credential)


def test_download_delete_tag(client, admin_auth_header, download):
    _test_delete_tag(client, admin_auth_header, "/api/v2/downloads", download)


@pytest.fixture(scope="function")
def _create_tags(
    client,
    admin_auth_header,
    listener,
    agent,
    agent_task,
    plugin_task,
    credential,
    download,
):
    paths = [
        "/api/v2/listeners",
        "/api/v2/agents",
        f"/api/v2/agents/{agent_task['agent_id']}/tasks",
        "/api/v2/plugins/basic_reporting/tasks",
        "/api/v2/credentials",
        "/api/v2/downloads",
    ]
    cleanup = []
    expected_tags = []
    for taggable in zip(
        [listener, agent, agent_task, plugin_task, credential, download],
        paths,
    ):
        if isinstance(taggable[0], dict):
            taggable_id = taggable[0]["id"]
        else:
            taggable_id = taggable[0]
        resp = client.post(
            f"{taggable[1]}/{taggable_id}/tags",
            headers=admin_auth_header,
            json={"name": f"test_tag_{taggable[1]}", "value": "test_value"},
        )
        assert resp.status_code == 201

        res = resp.json()
        cleanup.append(f"{taggable[1]}/{taggable_id}/tags/{res['id']}")
        res.pop("id")
        expected_tags.append(res)

    yield expected_tags

    for tag in cleanup:
        resp = client.delete(tag, headers=admin_auth_header)
        assert resp.status_code == 204


def test_get_tags(client, admin_auth_header, _create_tags):
    expected_tags = _create_tags
    resp = client.get("/api/v2/tags?order_by=name", headers=admin_auth_header)
    assert resp.status_code == 200

    actual_tags = resp.json()["records"]
    for tag in actual_tags:
        tag.pop("id")

    expected_tags = sorted(expected_tags, key=lambda k: k["name"])
    assert actual_tags == expected_tags


@pytest.fixture(scope="function")
def _create_agent_tasks_with_tags(
    client, admin_auth_header, agent, session_local, models
):
    with session_local.begin() as db:
        db.query(models.AgentTask).delete()

    agent_id = agent
    agent_tasks = []
    tags = []
    for i in range(3):
        resp = client.post(
            f"/api/v2/agents/{agent_id}/tasks/shell",
            headers=admin_auth_header,
            json={"command": f"whoami_{i}"},
        )
        assert resp.status_code == 201
        agent_tasks.append(resp.json())

    for i, agent_task in enumerate(agent_tasks):
        resp = client.post(
            f"/api/v2/agents/{agent_id}/tasks/{agent_task['id']}/tags",
            headers=admin_auth_header,
            json={"name": f"test_tag_{i}", "value": f"test_value_{i}"},
        )
        assert resp.status_code == 201
        tags.append((agent_task, resp.json()))

    yield agent_tasks

    for task, tag in tags:
        resp = client.delete(
            f"/api/v2/agents/{agent_id}/tasks/{task['id']}/tags/{tag['id']}",
            headers=admin_auth_header,
        )
        assert resp.status_code == 204

    for agent_task in agent_tasks:
        resp = client.delete(
            f"/api/v2/agents/{agent_id}/tasks/{agent_task['id']}",
            headers=admin_auth_header,
        )
        assert resp.status_code == 204


def test_get_agent_tasks_tag_filter(
    client, admin_auth_header, agent, _create_agent_tasks_with_tags
):
    resp = client.get(f"/api/v2/agents/{agent}/tasks", headers=admin_auth_header)

    assert resp.status_code == 200
    assert len(resp.json()["records"]) == 3

    resp = client.get(
        f"/api/v2/agents/{agent}/tasks?tags=test_tag_0:test_value_0",
        headers=admin_auth_header,
    )

    assert resp.status_code == 200
    assert len(resp.json()["records"]) == 1
    assert resp.json()["records"][0]["input"] == "whoami_0"
    assert resp.json()["records"][0]["tags"][0]["name"] == "test_tag_0"

    resp = client.get(
        f"/api/v2/agents/{agent}/tasks?tags=test_tag_0:test_value_0&tags=test_tag_1:test_value_1",
        headers=admin_auth_header,
    )

    assert resp.status_code == 200
    assert len(resp.json()["records"]) == 2
    assert resp.json()["records"][1]["input"] == "whoami_0"
    assert resp.json()["records"][1]["tags"][0]["name"] == "test_tag_0"
    assert resp.json()["records"][0]["input"] == "whoami_1"
    assert resp.json()["records"][0]["tags"][0]["name"] == "test_tag_1"

    # Test tag value bad
    resp = client.get(
        f"/api/v2/agents/{agent}/tasks?tags=test_tag_0", headers=admin_auth_header
    )

    assert resp.status_code == 422
    assert (
        resp.json()["detail"][0]["msg"] == 'string does not match regex "^[^:]+:[^:]+$"'
    )


@pytest.fixture(scope="function")
def _create_plugin_tasks_with_tags(
    models, session_local, client, admin_auth_header, plugin_name
):
    plugin_tasks = []
    tags = []
    for i in range(3):
        plugin_task = models.PluginTask(
            plugin_id=plugin_name,
            input=f"input {i}",
            input_full=f"input {i}",
            user_id=None,
            status=PluginTaskStatus.completed,
        )
        with session_local.begin() as db:
            db.add(plugin_task)
            db.flush()
            plugin_tasks.append({"id": plugin_task.id})

    for i, plugin_task in enumerate(plugin_tasks):
        resp = client.post(
            f"/api/v2/plugins/{plugin_name}/tasks/{plugin_task['id']}/tags",
            headers=admin_auth_header,
            json={"name": f"test_tag_{i}", "value": f"test_value_{i}"},
        )
        assert resp.status_code == 201
        tags.append((plugin_task, resp.json()))

    yield plugin_tasks

    for task, tag in tags:
        resp = client.delete(
            f"/api/v2/plugins/{plugin_name}/tasks/{task['id']}/tags/{tag['id']}",
            headers=admin_auth_header,
        )
        assert resp.status_code == 204

    with session_local.begin() as db:
        db.query(models.PluginTask).delete()


def test_get_plugin_tasks_tag_filter(
    client, admin_auth_header, plugin_name, _create_plugin_tasks_with_tags
):
    resp = client.get(f"/api/v2/plugins/{plugin_name}/tasks", headers=admin_auth_header)

    assert resp.status_code == 200
    assert len(resp.json()["records"]) == 3

    resp = client.get(
        f"/api/v2/plugins/{plugin_name}/tasks?tags=test_tag_0:test_value_0",
        headers=admin_auth_header,
    )

    assert resp.status_code == 200
    assert len(resp.json()["records"]) == 1
    assert resp.json()["records"][0]["input"] == "input 0"
    assert resp.json()["records"][0]["tags"][0]["name"] == "test_tag_0"

    resp = client.get(
        f"/api/v2/plugins/{plugin_name}/tasks?tags=test_tag_0:test_value_0&tags=test_tag_1:test_value_1",
        headers=admin_auth_header,
    )

    assert resp.status_code == 200
    assert len(resp.json()["records"]) == 2
    assert resp.json()["records"][1]["input"] == "input 0"
    assert resp.json()["records"][1]["tags"][0]["name"] == "test_tag_0"
    assert resp.json()["records"][0]["input"] == "input 1"
    assert resp.json()["records"][0]["tags"][0]["name"] == "test_tag_1"

    # Test tag value bad
    resp = client.get(
        f"/api/v2/plugins/{plugin_name}/tasks?tags=test_tag_0",
        headers=admin_auth_header,
    )

    assert resp.status_code == 422
    assert (
        resp.json()["detail"][0]["msg"] == 'string does not match regex "^[^:]+:[^:]+$"'
    )


@pytest.fixture(scope="function")
def _create_downloads_with_tags(models, session_local, client, admin_auth_header):
    downloads = []
    tags = []
    with session_local.begin() as db:
        # Unsure why this is needed, but it is.
        # Some other test must be adding a download and not removing it.
        db.query(models.upload_download_assc).delete()
        db.query(models.Download).delete()

    for i in range(3):
        download = models.Download(
            location=f"path/{i}", filename=f"filename_{i}", size=1
        )
        with session_local.begin() as db:
            db.add(download)
            db.flush()
            downloads.append({"id": download.id})

    for i, download in enumerate(downloads):
        resp = client.post(
            f"/api/v2/downloads/{download['id']}/tags",
            headers=admin_auth_header,
            json={"name": f"test_tag_{i}", "value": f"test_value_{i}"},
        )
        assert resp.status_code == 201
        tags.append(resp.json())

    yield downloads

    for tag in tags:
        resp = client.delete(
            f"/api/v2/downloads/{downloads[0]['id']}/tags/{tag['id']}",
            headers=admin_auth_header,
        )
        assert resp.status_code == 204

    with session_local.begin() as db:
        db.query(models.download_tag_assc).delete()
        db.query(models.Download).delete()


def test_get_downloads_tag_filter(
    client, admin_auth_header, _create_downloads_with_tags
):
    resp = client.get("/api/v2/downloads/", headers=admin_auth_header)

    assert resp.status_code == 200

    assert len(resp.json()["records"]) == 3

    resp = client.get(
        "/api/v2/downloads?tags=test_tag_0:test_value_0",
        headers=admin_auth_header,
    )

    assert resp.status_code == 200
    assert len(resp.json()["records"]) == 1
    assert resp.json()["records"][0]["location"] == "path/0"
    assert resp.json()["records"][0]["tags"][0]["name"] == "test_tag_0"

    resp = client.get(
        "/api/v2/downloads?tags=test_tag_0:test_value_0&tags=test_tag_1:test_value_1",
        headers=admin_auth_header,
    )

    assert resp.status_code == 200
    assert len(resp.json()["records"]) == 2

    record_0 = next(filter(lambda x: x["location"] == "path/0", resp.json()["records"]))
    record_1 = next(filter(lambda x: x["location"] == "path/1", resp.json()["records"]))

    assert record_0
    assert record_0["location"] == "path/0"
    assert record_0["tags"][0]["name"] == "test_tag_0"

    assert record_1
    assert record_1["location"] == "path/1"
    assert record_1["tags"][0]["name"] == "test_tag_1"

    # Test tag value bad
    resp = client.get("/api/v2/downloads?tags=test_tag_0", headers=admin_auth_header)

    assert resp.status_code == 422
    assert (
        resp.json()["detail"][0]["msg"] == 'string does not match regex "^[^:]+:[^:]+$"'
    )
