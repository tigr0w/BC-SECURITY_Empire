# todo refactor this out
my_globals = {"listener_id": 0}


def test_get_listener_templates(client, admin_auth_header):
    response = client.get(
        "/api/v2beta/listener-templates/",
        headers=admin_auth_header,
    )
    assert response.status_code == 200
    assert len(response.json()["records"]) >= 8


def test_get_listener_template(client, admin_auth_header):
    response = client.get(
        "/api/v2beta/listener-templates/http",
        headers=admin_auth_header,
    )
    assert response.status_code == 200
    assert response.json()["name"] == "HTTP[S]"
    assert response.json()["id"] == "http"
    assert type(response.json()["options"]) == dict


def test_create_listener_validation_fails_required_field(
    client, base_listener, admin_auth_header
):
    base_listener["options"]["Port"] = ""
    response = client.post(
        "/api/v2beta/listeners/", headers=admin_auth_header, json=base_listener
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "required option missing: Port"


# todo there are no listeners with strict fields. need to fake it somehow, or just wait until
#   we have one to worry about testing.
# def test_create_listener_validation_fails_strict_field():
#     listener = get_base_listener()
#     listener['options']['Port'] = ''
#     response = client.post("/api/v2beta/listeners/", json=listener)
#     assert response.status_code == 400
#     assert response.json()['detail'] == 'required listener option missing: Port'


def test_create_listener_custom_validation_fails(
    client, base_listener, admin_auth_header
):
    base_listener["options"]["Host"] = "https://securedomain.com"
    response = client.post(
        "/api/v2beta/listeners/", headers=admin_auth_header, json=base_listener
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "[!] HTTPS selected but no CertPath specified."


def test_create_listener_template_not_found(client, base_listener, admin_auth_header):
    base_listener["template"] = "qwerty"

    response = client.post(
        "/api/v2beta/listeners/", headers=admin_auth_header, json=base_listener
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Listener Template qwerty not found"


def test_create_listener(client, base_listener, admin_auth_header):
    # test that it ignore extra params
    base_listener["options"]["xyz"] = "xyz"

    response = client.post(
        "/api/v2beta/listeners/", headers=admin_auth_header, json=base_listener
    )
    assert response.status_code == 201
    assert response.json()["options"].get("xyz") is None

    assert response.json()["options"]["Name"] == base_listener["options"]["Name"]
    assert response.json()["options"]["Port"] == base_listener["options"]["Port"]
    assert (
        response.json()["options"]["DefaultJitter"]
        == base_listener["options"]["DefaultJitter"]
    )
    assert (
        response.json()["options"]["DefaultDelay"]
        == base_listener["options"]["DefaultDelay"]
    )

    my_globals["listener_id"] = response.json()["id"]


def test_create_listener_name_conflict(client, base_listener, admin_auth_header):
    response = client.post(
        "/api/v2beta/listeners/", headers=admin_auth_header, json=base_listener
    )
    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == f"Listener with name {base_listener['name']} already exists."
    )


def test_get_listener(client, admin_auth_header):
    response = client.get(
        f"/api/v2beta/listeners/{my_globals['listener_id']}",
        headers=admin_auth_header,
    )
    assert response.status_code == 200
    assert response.json()["id"] == my_globals["listener_id"]


def test_get_listener_not_found(client, admin_auth_header):
    response = client.get(
        "/api/v2beta/listeners/9999",
        headers=admin_auth_header,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Listener not found for id 9999"


def test_update_listener_not_found(client, base_listener, admin_auth_header):
    base_listener["enabled"] = False
    response = client.put(
        "/api/v2beta/listeners/9999", headers=admin_auth_header, json=base_listener
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Listener not found for id 9999"


def test_update_listener_blocks_while_enabled(client, admin_auth_header):
    response = client.get(
        f"/api/v2beta/listeners/{my_globals['listener_id']}",
        headers=admin_auth_header,
    )
    assert response.json()["enabled"] is True

    response = client.put(
        f"/api/v2beta/listeners/{my_globals['listener_id']}",
        headers=admin_auth_header,
        json=response.json(),
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Listener must be disabled before modifying"


def test_update_listener_allows_and_disables_while_enabled(client, admin_auth_header):
    response = client.get(
        f"/api/v2beta/listeners/{my_globals['listener_id']}",
        headers=admin_auth_header,
    )
    assert response.json()["enabled"] is True

    listener = response.json()
    listener["enabled"] = False
    new_port = str(int(listener["options"]["Port"]) + 1)
    listener["options"]["Port"] = new_port
    response = client.put(
        f"/api/v2beta/listeners/{my_globals['listener_id']}",
        headers=admin_auth_header,
        json=listener,
    )
    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert response.json()["options"]["Port"] == new_port


def test_update_listener_allows_while_disabled(client, admin_auth_header):
    response = client.get(
        f"/api/v2beta/listeners/{my_globals['listener_id']}", headers=admin_auth_header
    )
    assert response.json()["enabled"] is False

    listener = response.json()
    new_port = str(int(listener["options"]["Port"]) + 1)
    listener["options"]["Port"] = new_port
    # test that it ignore extra params
    listener["options"]["xyz"] = "xyz"

    response = client.put(
        f"/api/v2beta/listeners/{my_globals['listener_id']}",
        headers=admin_auth_header,
        json=listener,
    )
    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert response.json()["options"]["Port"] == new_port
    assert response.json()["options"].get("xyz") is None


def test_update_listener_name_conflict(client, base_listener, admin_auth_header):
    # Create a second listener.
    base_listener["name"] = "new-listener-2"
    base_listener["options"]["Port"] = "1299"
    response = client.post(
        "/api/v2beta/listeners/", headers=admin_auth_header, json=base_listener
    )
    assert response.status_code == 201

    created = response.json()
    created["enabled"] = False
    response = client.put(
        f"/api/v2beta/listeners/{created['id']}",
        headers=admin_auth_header,
        json=created,
    )
    assert response.status_code == 200

    created["name"] = "new-listener-1"
    response = client.put(
        f"/api/v2beta/listeners/{created['id']}",
        headers=admin_auth_header,
        json=created,
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"] == "Listener with name new-listener-1 already exists."
    )


def test_update_listener_reverts_if_validation_fails(client, admin_auth_header):
    response = client.get(
        f"/api/v2beta/listeners/{my_globals['listener_id']}",
        headers=admin_auth_header,
    )
    assert response.json()["enabled"] is False

    listener = response.json()
    del listener["options"]["Host"]
    listener["options"]["BindIP"] = "1.1.1.1"
    response = client.put(
        f"/api/v2beta/listeners/{listener['id']}",
        headers=admin_auth_header,
        json=listener,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "required option missing: Host"

    response = client.get(
        f"/api/v2beta/listeners/{my_globals['listener_id']}", headers=admin_auth_header
    )
    assert response.json()["options"]["BindIP"] == "0.0.0.0"


def test_update_listener_reverts_if_custom_validation_fails(client, admin_auth_header):
    response = client.get(
        f"/api/v2beta/listeners/{my_globals['listener_id']}",
        headers=admin_auth_header,
    )
    assert response.json()["enabled"] is False

    listener = response.json()
    listener["options"]["Host"] = "https://securesite.com"
    listener["options"]["BindIP"] = "1.1.1.1"
    response = client.put(
        f"/api/v2beta/listeners/{listener['id']}",
        headers=admin_auth_header,
        json=listener,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "[!] HTTPS selected but no CertPath specified."

    response = client.get(
        f"/api/v2beta/listeners/  {my_globals['listener_id']}",
        headers=admin_auth_header,
    )
    assert response.json()["options"]["BindIP"] == "0.0.0.0"


def test_update_listener_allows_and_enables_while_disabled(client, admin_auth_header):
    response = client.get(
        f"/api/v2beta/listeners/{my_globals['listener_id']}",
        headers=admin_auth_header,
    )
    assert response.json()["enabled"] is False

    listener = response.json()
    new_port = str(int(listener["options"]["Port"]) + 1)
    listener["enabled"] = True
    listener["options"]["Port"] = new_port
    response = client.put(
        f"/api/v2beta/listeners/{my_globals['listener_id']}",
        headers=admin_auth_header,
        json=listener,
    )
    assert response.status_code == 200
    assert response.json()["enabled"] is True
    assert response.json()["options"]["Port"] == new_port


def test_get_listeners(client, admin_auth_header):
    response = client.get(f"/api/v2beta/listeners", headers=admin_auth_header)

    assert response.status_code == 200
    assert len(response.json()["records"]) == 2


def test_delete_listener_while_enabled(client, admin_auth_header):
    response = client.get(f"/api/v2beta/listeners", headers=admin_auth_header)
    assert response.status_code == 200
    assert len(response.json()["records"]) == 2

    to_delete = list(
        filter(lambda x: x["enabled"] is True, response.json()["records"])
    )[0]
    assert to_delete["enabled"] is True

    response = client.delete(
        f"/api/v2beta/listeners/{to_delete['id']}", headers=admin_auth_header
    )
    assert response.status_code == 204

    response = client.get(
        f"/api/v2beta/listeners",
        headers=admin_auth_header,
    )
    assert response.status_code == 200
    assert len(response.json()["records"]) == 1
    assert response.json()["records"][0]["id"] != to_delete["id"]


def test_delete_listener_while_disabled(client, admin_auth_header):
    response = client.get(
        f"/api/v2beta/listeners",
        headers=admin_auth_header,
    )
    assert response.status_code == 200
    assert len(response.json()["records"]) == 1

    to_delete = response.json()["records"][0]
    assert to_delete["enabled"] is False

    response = client.delete(
        f"/api/v2beta/listeners/{to_delete['id']}",
        headers=admin_auth_header,
    )
    assert response.status_code == 204

    response = client.get(
        f"/api/v2beta/listeners",
        headers=admin_auth_header,
    )
    assert response.status_code == 200
    assert len(response.json()["records"]) == 0
