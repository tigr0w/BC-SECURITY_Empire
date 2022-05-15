def test_get_plugin_not_found(client, admin_auth_header):
    response = client.get("/api/v2beta/plugins/some_plugin", headers=admin_auth_header)

    assert response.status_code == 404
    assert response.json()["detail"] == "Plugin not found for id some_plugin"


def test_get_plugin(client, admin_auth_header):
    response = client.get(
        "/api/v2beta/plugins/basic_reporting", headers=admin_auth_header
    )

    assert response.status_code == 200
    assert response.json()["name"] == "basic_reporting"
    assert (
        response.json()["description"]
        == "Generates credentials.csv, sessions.csv, and master.log. Writes to server/data directory."
    )


def test_get_plugins(client, admin_auth_header):
    response = client.get("/api/v2beta/plugins", headers=admin_auth_header)

    assert response.status_code == 200
    assert len(response.json()["records"]) > 0


def test_execute_plugin_not_found(client, admin_auth_header):
    response = client.post(
        "/api/v2beta/plugins/some_plugin/execute", headers=admin_auth_header
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Plugin not found for id some_plugin"


def test_execute_plugin_validation_failed(client, admin_auth_header):
    response = client.post(
        "/api/v2beta/plugins/websockify/execute",
        json={
            "options": {
                "SourceHost": "0.0.0.0",
                "SourcePort": "5910",
                "TargetHost": "0.0.0.0",
                "TargetPort": "5910",
            }
        },
        headers=admin_auth_header,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "required option missing: Status"


def test_execute_plugin_raises_exception(client, admin_auth_header, main_menu):
    old_execute = main_menu.pluginsv2.loaded_plugins["basic_reporting"].execute
    main_menu.pluginsv2.loaded_plugins["basic_reporting"].execute = lambda x: 1 / 0

    response = client.post(
        "/api/v2beta/plugins/basic_reporting/execute",
        json={"options": {}},
        headers=admin_auth_header,
    )

    main_menu.pluginsv2.loaded_plugins["basic_reporting"].execute = old_execute

    assert response.status_code == 500
    assert response.json()["detail"] == "internal plugin error"


def test_execute_plugin_returns_zero(client, admin_auth_header, main_menu):
    old_execute = main_menu.pluginsv2.loaded_plugins["basic_reporting"].execute
    main_menu.pluginsv2.loaded_plugins["basic_reporting"].execute = lambda x: False

    response = client.post(
        "/api/v2beta/plugins/basic_reporting/execute",
        json={"options": {}},
        headers=admin_auth_header,
    )

    main_menu.pluginsv2.loaded_plugins["basic_reporting"].execute = old_execute

    assert response.status_code == 500
    assert response.json()["detail"] == "internal plugin error"


def test_execute_plugin(client, admin_auth_header):
    response = client.post(
        "/api/v2beta/plugins/basic_reporting/execute",
        json={"options": {}},
        headers=admin_auth_header,
    )

    assert response.status_code == 200
    assert response.json() == {}  # todo vr what should execution response look like?
