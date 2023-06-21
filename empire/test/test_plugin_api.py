from contextlib import contextmanager


@contextmanager
def patch_plugin_execute(main, plugin_name, execute_func):
    old_execute = main.pluginsv2.loaded_plugins[plugin_name].execute
    main.pluginsv2.loaded_plugins[plugin_name].execute = execute_func
    yield
    main.pluginsv2.loaded_plugins[plugin_name].execute = old_execute


def test_get_plugin_not_found(client, admin_auth_header):
    response = client.get("/api/v2/plugins/some_plugin", headers=admin_auth_header)

    assert response.status_code == 404
    assert response.json()["detail"] == "Plugin not found for id some_plugin"


def test_get_plugin(client, admin_auth_header):
    response = client.get("/api/v2/plugins/basic_reporting", headers=admin_auth_header)

    assert response.status_code == 200
    assert response.json()["name"] == "basic_reporting"
    assert (
        response.json()["description"]
        == "Generates credentials.csv, sessions.csv, and master.log. Writes to server/data directory."
    )


def test_get_plugins(client, admin_auth_header):
    response = client.get("/api/v2/plugins", headers=admin_auth_header)

    assert response.status_code == 200
    assert len(response.json()["records"]) > 0


def test_execute_plugin_not_found(client, admin_auth_header):
    response = client.post(
        "/api/v2/plugins/some_plugin/execute", headers=admin_auth_header
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Plugin not found for id some_plugin"


def test_execute_plugin_validation_failed(client, admin_auth_header):
    response = client.post(
        "/api/v2/plugins/websockify_server/execute",
        json={
            "options": {
                "SourceHost": "0.0.0.0",
                "SourcePort": "5910",
                "TargetPort": "5910",
                "Status": "stop",
            }
        },
        headers=admin_auth_header,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "required option missing: TargetHost"


def test_execute_plugin_raises_exception(client, admin_auth_header, main):
    with patch_plugin_execute(main, "basic_reporting", lambda x: 1 / 0):
        response = client.post(
            "/api/v2/plugins/basic_reporting/execute",
            json={"options": {}},
            headers=admin_auth_header,
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "internal plugin error"


def test_execute_plugin_returns_false(client, admin_auth_header, main):
    with patch_plugin_execute(main, "basic_reporting", lambda x: False):
        response = client.post(
            "/api/v2/plugins/basic_reporting/execute",
            json={"options": {}},
            headers=admin_auth_header,
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "internal plugin error"


def test_execute_plugin(client, admin_auth_header, main):
    with patch_plugin_execute(
        main, "basic_reporting", lambda x: "Successful Execution"
    ):
        response = client.post(
            "/api/v2/plugins/basic_reporting/execute",
            json={"options": {}},
            headers=admin_auth_header,
        )

    assert response.status_code == 200
    assert response.json() == {"detail": "Successful Execution"}


def test_reload_plugins(client, admin_auth_header):
    # Get initial list of plugins
    initial_response = client.get("/api/v2/plugins", headers=admin_auth_header)
    initial_plugins = initial_response.json()["records"]

    # Call the reload plugins endpoint
    response = client.post("/api/v2/plugins/reload", headers=admin_auth_header)
    assert response.status_code == 204

    # Get the list of plugins after reloading
    final_response = client.get("/api/v2/plugins", headers=admin_auth_header)
    final_plugins = final_response.json()["records"]

    # The initial and final list of plugins should be the same after reload
    assert len(initial_plugins) == len(final_plugins)
