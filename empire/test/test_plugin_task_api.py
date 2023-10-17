import pytest


@pytest.fixture(scope="module", autouse=True)
def plugin_task_1(main, session_local, models, plugin_name):
    with session_local.begin() as db:
        task = models.PluginTask(
            plugin_id=plugin_name,
            input="This is the trimmed input for the task.",
            input_full="This is the full input for the task.",
            user_id=1,
        )
        db.add(task)
        db.flush()

        task_id = task.id

    yield task_id

    with session_local.begin() as db:
        db.query(models.PluginTask).delete()


def test_get_tasks_for_plugin_not_found(client, admin_auth_header):
    response = client.get("/api/v2/plugins/abc/tasks", headers=admin_auth_header)
    assert response.status_code == 404
    assert response.json()["detail"] == "Plugin not found for id abc"


def test_get_tasks_for_plugin(client, admin_auth_header, plugin_name):
    response = client.get(
        f"/api/v2/plugins/{plugin_name}/tasks", headers=admin_auth_header
    )
    assert response.status_code == 200
    assert len(response.json()["records"]) > 0
    assert (
        len(
            list(
                filter(
                    lambda x: x["plugin_id"] != plugin_name,
                    response.json()["records"],
                )
            )
        )
        == 0
    )


def test_get_task_for_plugin_plugin_not_found(client, admin_auth_header):
    response = client.get("/api/v2/plugins/abc/tasks/1", headers=admin_auth_header)
    assert response.status_code == 404
    assert response.json()["detail"] == "Plugin not found for id abc"


def test_get_task_for_plugin_not_found(client, admin_auth_header, plugin_name):
    response = client.get(
        f"/api/v2/plugins/{plugin_name}/tasks/9999", headers=admin_auth_header
    )
    assert response.status_code == 404
    assert (
        response.json()["detail"]
        == f"Task not found for plugin {plugin_name} and task id 9999"
    )


def test_get_task_for_plugin(client, admin_auth_header, plugin_name, db, plugin_task_1):
    response = client.get(
        f"/api/v2/plugins/{plugin_name}/tasks/{plugin_task_1}",
        headers=admin_auth_header,
    )
    assert response.status_code == 200
    assert response.json()["id"] == plugin_task_1
    assert response.json()["plugin_id"] == plugin_name
