def test_get_module_not_found(client, admin_auth_header):
    response = client.get("/api/v2/modules/some_module", headers=admin_auth_header)

    assert response.status_code == 404
    assert response.json()["detail"] == "Module not found for id some_module"


def test_get_module(client, admin_auth_header):
    uid = "python_trollsploit_osx_say"
    response = client.get(f"/api/v2/modules/{uid}", headers=admin_auth_header)

    assert response.status_code == 200
    assert response.json()["id"] == uid
    assert response.json()["name"] == "Say"


def test_get_module_script_module_not_found(client, admin_auth_header):
    uid = "this_module_does_not_exist"
    response = client.get(f"/api/v2/modules/{uid}/script", headers=admin_auth_header)

    assert response.status_code == 404
    assert response.json()["detail"] == f"Module not found for id {uid}"


def test_get_module_script_in_yaml(client, admin_auth_header):
    uid = "python_trollsploit_osx_say"
    response = client.get(f"/api/v2/modules/{uid}/script", headers=admin_auth_header)

    assert response.status_code == 200
    assert response.json()["module_id"] == uid
    assert response.json()["script"].startswith(
        "run_command('say -v {{ Voice }} {{ Text }}')"
    )


def test_get_module_script_in_path(client, admin_auth_header):
    uid = "powershell_code_execution_invoke_boolang"
    response = client.get(f"/api/v2/modules/{uid}/script", headers=admin_auth_header)

    assert response.status_code == 200
    assert response.json()["module_id"] == uid
    assert response.json()["script"].startswith("function Invoke-Boolang")


def test_get_module_script_in_generate_function(client, admin_auth_header):
    uid = "python_collection_osx_imessage_dump"
    response = client.get(f"/api/v2/modules/{uid}/script", headers=admin_auth_header)

    assert response.status_code == 404
    assert response.json()["detail"] == f"Module script not found for id {uid}"


def test_get_modules(client, admin_auth_header):
    response = client.get("/api/v2/modules/", headers=admin_auth_header)

    assert response.status_code == 200

    assert len(response.json()["records"]) >= 383


def test_update_module(client, admin_auth_header):
    uid = "python_trollsploit_osx_say"
    response = client.put(
        f"/api/v2/modules/{uid}", headers=admin_auth_header, json={"enabled": False}
    )

    assert response.status_code == 200

    response = client.get(f"/api/v2/modules/{uid}", headers=admin_auth_header)

    assert response.status_code == 200
    assert response.json()["enabled"] is False

    response = client.put(
        f"/api/v2/modules/{uid}", headers=admin_auth_header, json={"enabled": True}
    )

    assert response.status_code == 200
    assert response.json()["enabled"] is True


def test_update_modules_bulk(client, admin_auth_header):
    uids = [
        "python_trollsploit_osx_say",
        "powershell_code_execution_invoke_boolang",
        "powershell_code_execution_invoke_ironpython",
    ]
    response = client.put(
        "/api/v2/modules/bulk/enable",
        headers=admin_auth_header,
        json={
            "enabled": False,
            "modules": uids,
        },
    )

    assert response.status_code == 204

    for uid in uids:
        response = client.get(f"/api/v2/modules/{uid}", headers=admin_auth_header)

        assert response.status_code == 200
        assert response.json()["enabled"] is False

    response = client.put(
        "/api/v2/modules/bulk/enable",
        headers=admin_auth_header,
        json={
            "enabled": True,
            "modules": uids,
        },
    )

    assert response.status_code == 204
