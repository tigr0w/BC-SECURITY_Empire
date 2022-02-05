import pytest

from empire.test.conftest import base_listener_non_fixture

# todo refactor this out
my_globals = {"stager_id_1": 0, "stager_id_2": 0}


@pytest.fixture(scope="module", autouse=True)
def create_listener(client, admin_auth_header):
    # not using fixture because scope issues
    response = client.post(
        "/api/v2beta/listeners/",
        headers=admin_auth_header,
        json=base_listener_non_fixture(),
    )
    return response.json()


def test_get_stager_templates(client, admin_auth_header):
    response = client.get(
        "/api/v2beta/stager-templates/",
        headers=admin_auth_header,
    )
    assert response.status_code == 200
    assert len(response.json()["records"]) == 37


def test_get_stager_template(client, admin_auth_header):
    response = client.get(
        "/api/v2beta/stager-templates/multi_launcher",
        headers=admin_auth_header,
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Launcher"
    assert response.json()["id"] == "multi_launcher"
    assert type(response.json()["options"]) == dict


def test_create_stager_validation_fails_required_field(
    client, base_stager, admin_auth_header
):
    base_stager["options"]["Listener"] = ""
    response = client.post(
        "/api/v2beta/stagers/", headers=admin_auth_header, json=base_stager
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "required stager option missing: Listener"


def test_create_stager_validation_fails_strict_field(
    client, base_stager, admin_auth_header
):
    base_stager["options"]["Language"] = ""
    response = client.post(
        "/api/v2beta/stagers/", headers=admin_auth_header, json=base_stager
    )
    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "Language must be set to one of the suggested values."
    )


# def test_create_stager_custom_validation_fails():
#     stager = get_base_stager()
#     stager['options']['Language'] = 'powershell'
#     response = client.post("/api/v2beta/stagers/", json=stager)
#     assert response.status_code == 400
#     assert response.json()['detail'] == 'Error generating'


def test_create_stager_template_not_found(client, base_stager, admin_auth_header):
    base_stager["template"] = "qwerty"

    response = client.post(
        "/api/v2beta/stagers/", headers=admin_auth_header, json=base_stager
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Stager Template qwerty not found"


def test_create_stager_one_liner(client, base_stager, admin_auth_header):
    # test that it ignore extra params
    base_stager["options"]["xyz"] = "xyz"

    response = client.post(
        "/api/v2beta/stagers/?save=true", headers=admin_auth_header, json=base_stager
    )
    assert response.status_code == 201
    assert response.json()["options"].get("xyz") is None
    assert len(response.json().get("downloads", [])) > 0
    assert (
        response.json()
        .get("downloads", [])[0]["link"]
        .startswith("/api/v2beta/downloads")
    )  # todo should a oneliner have a download link or be embedded??

    my_globals["stager_id_1"] = response.json()["id"]


def test_create_stager_file(client, base_stager_2, admin_auth_header):
    # test that it ignore extra params
    base_stager_2["options"]["xyz"] = "xyz"

    response = client.post(
        "/api/v2beta/stagers/?save=true", headers=admin_auth_header, json=base_stager_2
    )
    assert response.status_code == 201
    assert response.json()["options"].get("xyz") is None
    assert len(response.json().get("downloads", [])) > 0
    assert (
        response.json()
        .get("downloads", [])[0]["link"]
        .startswith("/api/v2beta/downloads")
    )

    my_globals["stager_id_2"] = response.json()["id"]


def test_create_stager_name_conflict(client, base_stager, admin_auth_header):
    response = client.post(
        "/api/v2beta/stagers/?save=true", headers=admin_auth_header, json=base_stager
    )
    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == f'Stager with name {base_stager["name"]} already exists.'
    )


def test_create_stager_save_false(client, base_stager, admin_auth_header):
    response = client.post(
        "/api/v2beta/stagers/?save=false", headers=admin_auth_header, json=base_stager
    )
    assert response.status_code == 201
    assert response.json()["id"] == 0
    assert len(response.json().get("downloads", [])) > 0
    assert (
        response.json()
        .get("downloads", [])[0]["link"]
        .startswith("/api/v2beta/downloads")
    )


def test_get_stager(client, admin_auth_header):
    response = client.get(
        f"/api/v2beta/stagers/{my_globals['stager_id_1']}",
        headers=admin_auth_header,
    )
    assert response.status_code == 200
    assert response.json()["id"] == my_globals["stager_id_1"]


def test_get_stager_not_found(client, admin_auth_header):
    response = client.get(
        "/api/v2beta/stagers/9999",
        headers=admin_auth_header,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Stager not found for id 9999"


def test_update_stager_not_found(client, base_stager, admin_auth_header):
    response = client.put(
        "/api/v2beta/stagers/9999", headers=admin_auth_header, json=base_stager
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Stager not found for id 9999"


def test_download_stager_one_liner(client, admin_auth_header):
    response = client.get(
        f"/api/v2beta/stagers/{my_globals['stager_id_1']}",
        headers=admin_auth_header,
    )
    response = client.get(
        response.json()["downloads"][0]["link"],
        headers=admin_auth_header,
    )
    assert response.status_code == 200
    assert response.headers.get("content-type").split(";")[0] == "text/plain"
    assert response.text.startswith("powershell -noP -sta")


def test_download_stager_file(client, admin_auth_header):
    response = client.get(
        f"/api/v2beta/stagers/{my_globals['stager_id_2']}",
        headers=admin_auth_header,
    )
    response = client.get(
        response.json()["downloads"][0]["link"],
        headers=admin_auth_header,
    )
    assert response.status_code == 200
    assert (
        response.headers.get("content-type").split(";")[0] == "application/x-msdownload"
    )
    assert type(response.content) == bytes


def test_update_stager_allows_edits_and_generates_new_file(client, admin_auth_header):
    response = client.get(
        f"/api/v2beta/stagers/{my_globals['stager_id_1']}",
        headers=admin_auth_header,
    )
    assert response.status_code == 200

    stager = response.json()
    original_name = stager["name"]
    stager["name"] = stager["name"] + "_updated!"
    stager["options"]["Base64"] = "False"

    response = client.put(
        f"/api/v2beta/stagers/{my_globals['stager_id_1']}",
        headers=admin_auth_header,
        json=stager,
    )
    assert response.status_code == 200
    assert response.json()["options"]["Base64"] == "False"
    assert response.json()["name"] == original_name + "_updated!"

    # should this assert compare the checksum of the first download to the second?
    # todo assert response.json()['download']


def test_update_stager_name_conflict(client, admin_auth_header):
    response = client.get(
        f"/api/v2beta/stagers/{my_globals['stager_id_1']}",
        headers=admin_auth_header,
    )
    assert response.status_code == 200

    response2 = client.get(
        f"/api/v2beta/stagers/{my_globals['stager_id_2']}",
        headers=admin_auth_header,
    )
    assert response.status_code == 200
    stager_1 = response.json()
    stager_2 = response2.json()

    stager_1["name"] = stager_2["name"]
    response = client.put(
        f"/api/v2beta/stagers/{my_globals['stager_id_1']}",
        headers=admin_auth_header,
        json=stager_1,
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == f"Stager with name {stager_2['name']} already exists."
    )


def test_get_stagers(client, admin_auth_header):
    response = client.get(
        f"/api/v2beta/stagers",
        headers=admin_auth_header,
    )

    assert response.status_code == 200
    assert len(response.json()["records"]) == 2


def test_delete_stager(client, admin_auth_header):
    response = client.get(
        f"/api/v2beta/stagers",
        headers=admin_auth_header,
    )
    assert response.status_code == 200
    assert len(response.json()["records"]) == 2

    to_delete = response.json()["records"][0]
    response = client.delete(
        f"/api/v2beta/stagers/{to_delete['id']}",
        headers=admin_auth_header,
    )
    assert response.status_code == 204

    response = client.get(
        f"/api/v2beta/stagers",
        headers=admin_auth_header,
    )
    assert response.status_code == 200
    assert len(response.json()["records"]) == 1
    assert response.json()["records"][0]["id"] != to_delete["id"]
