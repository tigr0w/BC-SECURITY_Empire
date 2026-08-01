from starlette import status

from empire.server.core.db.models import PluginTaskStatus

PLUGIN_ID = "basic_reporting"


def test_get_tasks_for_plugin_not_found(client, admin_auth_header):
    response = client.get("/api/v2/plugins/abc/tasks", headers=admin_auth_header)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Plugin not found for id abc"


def test_get_tasks_for_plugin(client, admin_auth_header, plugin_task):
    response = client.get(
        f"/api/v2/plugins/{PLUGIN_ID}/tasks", headers=admin_auth_header
    )
    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()["records"]) > 0
    assert all(x["plugin_id"] == PLUGIN_ID for x in response.json()["records"])


def test_get_tasks_for_plugin_through_all_endpoint(
    client, admin_auth_header, plugin_task
):
    response = client.get(
        "/api/v2/plugins/tasks",
        headers=admin_auth_header,
        params={"plugins": PLUGIN_ID},
    )
    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()["records"]) > 0
    assert all(x["plugin_id"] == PLUGIN_ID for x in response.json()["records"])


def test_get_task_for_plugin_plugin_not_found(client, admin_auth_header):
    response = client.get("/api/v2/plugins/abc/tasks/1", headers=admin_auth_header)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Plugin not found for id abc"


def test_get_task_for_plugin_not_found(client, admin_auth_header):
    response = client.get(
        f"/api/v2/plugins/{PLUGIN_ID}/tasks/9999", headers=admin_auth_header
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert (
        response.json()["detail"]
        == f"Task not found for plugin {PLUGIN_ID} and task id 9999"
    )


def test_get_task_for_plugin(client, admin_auth_header, plugin_task):
    response = client.get(
        f"/api/v2/plugins/{PLUGIN_ID}/tasks/{plugin_task}",
        headers=admin_auth_header,
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == plugin_task
    assert response.json()["plugin_id"] == PLUGIN_ID
    assert response.json()["plugin_options"] == {"report": "all"}


def test_get_tasks_for_plugin_status_filter(
    main, session_local, models, client, admin_auth_header
):
    """The `status` filter must compare against PluginTask.status, not
    AgentTask.status — `started` is a valid PluginTaskStatus with no
    AgentTaskStatus equivalent, so filtering on it against the wrong column
    would either crash (invalid enum bind) or cartesian-join and return the
    wrong tasks."""
    with session_local.begin() as db:
        started = models.PluginTask(
            plugin_id=PLUGIN_ID,
            input="started task",
            user_id=1,
            status=PluginTaskStatus.started,
        )
        completed = models.PluginTask(
            plugin_id=PLUGIN_ID,
            input="completed task",
            user_id=1,
            status=PluginTaskStatus.completed,
        )
        db.add_all([started, completed])
        db.flush()
        started_id, completed_id = started.id, completed.id

    response = client.get(
        f"/api/v2/plugins/{PLUGIN_ID}/tasks",
        headers=admin_auth_header,
        params={"status": "started"},
    )
    assert response.status_code == status.HTTP_200_OK
    ids = {t["id"] for t in response.json()["records"]}
    assert started_id in ids
    assert completed_id not in ids
