from contextlib import contextmanager

from starlette.status import (
    HTTP_200_OK,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_500_INTERNAL_SERVER_ERROR,
)

from empire.server.core.exceptions import (
    PluginExecutionException,
    PluginValidationException,
)


@contextmanager
def patch_plugin_execute(main, plugin_name, execute_func):
    old_execute = main.pluginsv2.loaded_plugins[plugin_name].execute
    main.pluginsv2.loaded_plugins[plugin_name].execute = execute_func
    yield
    main.pluginsv2.loaded_plugins[plugin_name].execute = old_execute


@contextmanager
def patch_plugin_on_start(main, plugin_name, on_start_func):
    old_on_start = main.pluginsv2.loaded_plugins[plugin_name].on_start
    main.pluginsv2.loaded_plugins[plugin_name].on_start = on_start_func
    yield
    main.pluginsv2.loaded_plugins[plugin_name].on_start = old_on_start


def test_get_plugin_not_found(client, admin_auth_header):
    response = client.get("/api/v2/plugins/some_plugin", headers=admin_auth_header)

    assert response.status_code == HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Plugin not found for id some_plugin"


def test_get_plugin(client, admin_auth_header):
    response = client.get("/api/v2/plugins/basic_reporting", headers=admin_auth_header)

    assert response.status_code == HTTP_200_OK
    assert response.json()["name"] == "basic_reporting"
    assert (
        response.json()["description"]
        == "Generates credentials.csv, sessions.csv, and master.log. Writes to server/data directory."
    )


def test_get_plugins(client, admin_auth_header):
    response = client.get("/api/v2/plugins", headers=admin_auth_header)

    assert response.status_code == HTTP_200_OK
    assert len(response.json()["records"]) > 0


def test_execute_plugin_not_found(client, admin_auth_header):
    response = client.post(
        "/api/v2/plugins/some_plugin/execute", headers=admin_auth_header
    )

    assert response.status_code == HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Plugin not found for id some_plugin"


def test_execute_plugin_validation_failed(client, admin_auth_header):
    response = client.post(
        "/api/v2/plugins/basic_reporting/execute",
        json={
            "options": {
                "report": "",
            }
        },
        headers=admin_auth_header,
    )

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "required option missing: report"


def test_execute_plugin_raises_exception(client, admin_auth_header, main):
    with patch_plugin_execute(main, "basic_reporting", lambda x, **kwargs: 1 / 0):
        response = client.post(
            "/api/v2/plugins/basic_reporting/execute",
            json={"options": {}},
            headers=admin_auth_header,
        )

    assert response.status_code == HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json()["detail"] == "division by zero"


def test_execute_plugin_returns_false(client, admin_auth_header, main):
    with patch_plugin_execute(main, "basic_reporting", lambda x, **kwargs: False):
        response = client.post(
            "/api/v2/plugins/basic_reporting/execute",
            json={"options": {}},
            headers=admin_auth_header,
        )

    assert response.status_code == HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json()["detail"] == "internal plugin error"


def test_execute_plugin_returns_false_with_string(client, admin_auth_header, main):
    with patch_plugin_execute(
        main, "basic_reporting", lambda x, **kwargs: (False, "This is the message")
    ):
        response = client.post(
            "/api/v2/plugins/basic_reporting/execute",
            json={"options": {}},
            headers=admin_auth_header,
        )

    assert response.status_code == HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json()["detail"] == "This is the message"


def test_execute_plugin_returns_string(client, admin_auth_header, main):
    with patch_plugin_execute(
        main, "basic_reporting", lambda x, **kwargs: "Successful Execution"
    ):
        response = client.post(
            "/api/v2/plugins/basic_reporting/execute",
            json={"options": {}},
            headers=admin_auth_header,
        )

    assert response.status_code == HTTP_200_OK
    assert response.json() == {"detail": "Successful Execution"}


def test_execute_plugin_returns_true(client, admin_auth_header, main):
    with patch_plugin_execute(main, "basic_reporting", lambda x, **kwargs: True):
        response = client.post(
            "/api/v2/plugins/basic_reporting/execute",
            json={"options": {}},
            headers=admin_auth_header,
        )

    assert response.status_code == HTTP_200_OK
    assert response.json() == {"detail": "Plugin executed successfully"}


def test_execute_plugin_returns_true_with_string(client, admin_auth_header, main):
    # Since the second value represents an err, the first value is ignored and this is treated as an error.
    with patch_plugin_execute(
        main, "basic_reporting", lambda x, **kwargs: (True, "This is the message")
    ):
        response = client.post(
            "/api/v2/plugins/basic_reporting/execute",
            json={"options": {}},
            headers=admin_auth_header,
        )

    assert response.status_code == HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json() == {"detail": "This is the message"}


def test_execute_plugin_raises_plugin_validation_exception(
    client, admin_auth_header, main
):
    def raise_():
        raise PluginValidationException("This is the message")

    with patch_plugin_execute(main, "basic_reporting", lambda x, **kwargs: raise_()):
        response = client.post(
            "/api/v2/plugins/basic_reporting/execute",
            json={"options": {}},
            headers=admin_auth_header,
        )

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json() == {"detail": "This is the message"}


def test_execute_plugin_raises_plugin_execution_exception(
    client, admin_auth_header, main
):
    def raise_():
        raise PluginExecutionException("This is the message")

    with patch_plugin_execute(main, "basic_reporting", lambda x, **kwargs: raise_()):
        response = client.post(
            "/api/v2/plugins/basic_reporting/execute",
            json={"options": {}},
            headers=admin_auth_header,
        )

    assert response.status_code == HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json() == {"detail": "This is the message"}


def test_execute_plugin_returns_none(client, admin_auth_header, main):
    with patch_plugin_execute(main, "basic_reporting", lambda x, **kwargs: None):
        response = client.post(
            "/api/v2/plugins/basic_reporting/execute",
            json={"options": {}},
            headers=admin_auth_header,
        )

    assert response.status_code == HTTP_200_OK
    assert response.json() == {"detail": "Plugin executed successfully"}


def test_reload_plugins(client, admin_auth_header):
    # Get initial list of plugins
    initial_response = client.get("/api/v2/plugins", headers=admin_auth_header)
    initial_plugins = initial_response.json()["records"]

    # Call the reload plugins endpoint
    response = client.post("/api/v2/plugins/reload", headers=admin_auth_header)
    assert response.status_code == HTTP_204_NO_CONTENT

    # Get the list of plugins after reloading
    final_response = client.get("/api/v2/plugins", headers=admin_auth_header)
    final_plugins = final_response.json()["records"]

    # The initial and final list of plugins should be the same after reload
    assert len(initial_plugins) == len(final_plugins)


def test_toggle_plugin_enabled(client, admin_auth_header, main, session_local):
    response = client.get("/api/v2/plugins/basic_reporting", headers=admin_auth_header)
    assert response.json()["enabled"] is True

    # Execute should work
    response = client.post(
        "/api/v2/plugins/basic_reporting/execute",
        json={"options": {}},
        headers=admin_auth_header,
    )
    assert response.status_code == HTTP_200_OK

    # Stop the plugin
    response = client.put(
        "/api/v2/plugins/basic_reporting",
        json={"enabled": False},
        headers=admin_auth_header,
    )
    assert response.status_code == HTTP_200_OK

    # Execute should fail
    response = client.post(
        "/api/v2/plugins/basic_reporting/execute",
        json={"options": {}},
        headers=admin_auth_header,
    )
    assert response.status_code == HTTP_400_BAD_REQUEST

    # Start the plugin
    response = client.put(
        "/api/v2/plugins/basic_reporting",
        json={"enabled": True},
        headers=admin_auth_header,
    )
    assert response.status_code == HTTP_200_OK

    response = client.get("/api/v2/plugins/basic_reporting", headers=admin_auth_header)
    assert response.json()["enabled"] is True


def test_toggle_plugin_enabled_causes_exception(client, admin_auth_header, main):
    def _raise(db):
        raise PluginExecutionException("Error Test Test")

    with patch_plugin_on_start(main, "basic_reporting", _raise):
        client.put(
            "/api/v2/plugins/basic_reporting",
            json={"enabled": False},
            headers=admin_auth_header,
        )

        response = client.put(
            "/api/v2/plugins/basic_reporting",
            json={"enabled": True},
            headers=admin_auth_header,
        )

        assert response.status_code == HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json() == {"detail": "Error Test Test"}

        response = client.get(
            "/api/v2/plugins/basic_reporting", headers=admin_auth_header
        )
        assert response.json()["enabled"] is False

    response = client.put(
        "/api/v2/plugins/basic_reporting",
        json={"enabled": True},
        headers=admin_auth_header,
    )
    assert response.status_code == HTTP_200_OK


def test_plugin_settings(client, admin_auth_header, main):
    response = client.get(
        "/api/v2/plugins/websockify_server", headers=admin_auth_header
    )
    assert response.status_code == HTTP_200_OK

    assert response.json()["settings_options"] == {
        "SourceHost": {
            "description": "Address of the source host.",
            "editable": True,
            "required": True,
            "value": "0.0.0.0",
            "strict": False,
            "suggested_values": [],
            "value_type": "STRING",
            "internal": False,
            "depends_on": [],
        },
        "SourcePort": {
            "description": "Port on source host.",
            "editable": True,
            "required": True,
            "value": "5910",
            "strict": False,
            "suggested_values": [],
            "value_type": "STRING",
            "internal": False,
            "depends_on": [],
        },
        "TargetHost": {
            "description": "Address of the target host.",
            "editable": True,
            "required": True,
            "value": "",
            "strict": False,
            "suggested_values": [],
            "value_type": "STRING",
            "internal": False,
            "depends_on": [],
        },
        "TargetPort": {
            "description": "Port on target host.",
            "editable": True,
            "required": True,
            "value": "5900",
            "strict": False,
            "suggested_values": [],
            "value_type": "STRING",
            "internal": False,
            "depends_on": [],
        },
    }

    assert response.json()["current_settings"] == {
        "SourceHost": "0.0.0.0",
        "SourcePort": "5910",
        "TargetHost": "",
        "TargetPort": "5900",
    }

    # Validation failure
    response = client.put(
        "/api/v2/plugins/websockify_server/settings",
        json={},  # Missing required fields
        headers=admin_auth_header,
    )

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json() == {"detail": "required option missing: TargetHost"}

    # Update the settings
    response = client.put(
        "/api/v2/plugins/websockify_server/settings",
        # The only field that is required and missing a default
        json={"TargetHost": "0.0.0.0"},
        headers=admin_auth_header,
    )

    assert response.status_code == HTTP_200_OK

    response = client.get(
        "/api/v2/plugins/websockify_server", headers=admin_auth_header
    )

    # Settings should be updated
    assert response.status_code == HTTP_200_OK
    assert response.json()["current_settings"] == {
        "SourceHost": "0.0.0.0",
        "SourcePort": "5910",
        "TargetHost": "0.0.0.0",
        "TargetPort": "5900",
    }


def test_plugin_settings_non_editable(client, admin_auth_header, main, session_local):
    with session_local() as db:
        # Check the initial value of the non-editable field
        internal_plugin = main.pluginsv2.loaded_plugins["example_2"]
        assert internal_plugin.current_settings(db) == {
            "SomeNonEditableSetting": "Hello World"
        }

        response = client.get("/api/v2/plugins/example_2", headers=admin_auth_header)
        assert response.status_code == HTTP_200_OK
        assert (
            response.json()["settings_options"]
            .get("SomeNonEditableSetting")
            .get("editable")
            is False
        )
        assert response.json()["current_settings"] == {
            "SomeNonEditableSetting": "Hello World"
        }

        # Trying to edit the field won't result in an error,
        # but it also won't do anything.
        response = client.put(
            "/api/v2/plugins/example_2/settings",
            json={"SomeNonEditableSetting": "new value"},
            headers=admin_auth_header,
        )
        assert response.status_code == HTTP_200_OK

        response = client.get("/api/v2/plugins/example_2", headers=admin_auth_header)
        assert response.status_code == HTTP_200_OK
        assert response.json()["current_settings"] == {
            "SomeNonEditableSetting": "Hello World"
        }


def test_plugin_state_internal(client, admin_auth_header, main, session_local):
    with session_local() as db:
        response = client.get("/api/v2/plugins/example_2", headers=admin_auth_header)
        assert response.status_code == HTTP_200_OK
        assert response.json()["settings_options"].get("SomeInternalSetting") is None

        internal_plugin = main.pluginsv2.loaded_plugins["example_2"]
        assert internal_plugin.current_internal_state(db) == {
            "SomeInternalSetting": "internal_state_value"
        }


def test_plugin_disabled_execution(client, admin_auth_header, main):
    internal_plugin = main.pluginsv2.loaded_plugins["basic_reporting"]
    internal_plugin.execution_enabled = False

    response = client.post(
        "/api/v2/plugins/basic_reporting/execute",
        json={"options": {}},
        headers=admin_auth_header,
    )

    # Assert that the plugin execution is disabled and returns the expected response
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json() == {"detail": "Plugin execution is disabled"}
