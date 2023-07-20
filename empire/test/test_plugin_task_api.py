import pytest


@pytest.fixture(scope="module", autouse=True)
def plugin_task_1(main, db, models, plugin_name):
    db.add(
        models.PluginTask(
            plugin_id=plugin_name,
            input="This is the trimmed input for the task.",
            input_full="This is the full input for the task.",
            user_id=1,
        )
    )
    db.commit()
    yield

    db.query(models.PluginTask).delete()
    db.commit()


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


def test_get_task_for_plugin(client, admin_auth_header, plugin_name, db):
    response = client.get(
        f"/api/v2/plugins/{plugin_name}/tasks/1", headers=admin_auth_header
    )
    assert response.status_code == 200
    assert response.json()["id"] == 1
    assert response.json()["plugin_id"] == plugin_name
