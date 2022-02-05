def test_get_module_not_found(client, admin_auth_header):
    response = client.get("/api/v2beta/modules/some_module", headers=admin_auth_header)

    assert response.status_code == 404
    assert response.json()["detail"] == "Module not found for id some_module"


def test_get_module(client, admin_auth_header):
    uid = "python_trollsploit_osx_say"
    response = client.get(f"/api/v2beta/modules/{uid}", headers=admin_auth_header)

    assert response.status_code == 200
    assert response.json()["id"] == uid
    assert response.json()["name"] == "Say"


def test_get_modules(client, admin_auth_header):
    response = client.get("/api/v2beta/modules/", headers=admin_auth_header)

    assert response.status_code == 200
    assert len(response.json()["records"]) >= 394


def test_update_module(client, admin_auth_header):
    uid = "python_trollsploit_osx_say"
    response = client.put(
        f"/api/v2beta/modules/{uid}", headers=admin_auth_header, json={"enabled": False}
    )

    assert response.status_code == 200

    response = client.get(f"/api/v2beta/modules/{uid}", headers=admin_auth_header)

    assert response.status_code == 200
    assert response.json()["enabled"] is False


def test_update_modules_bulk(client, admin_auth_header):
    uids = [
        "python_trollsploit_osx_say",
        "powershell_code_execution_invoke_boolang",
        "powershell_code_execution_invoke_ironpython",
    ]
    response = client.put(
        f"/api/v2beta/modules/bulk/enable",
        headers=admin_auth_header,
        json={
            "enabled": False,
            "modules": uids,
        },
    )

    assert response.status_code == 204

    for uid in uids:
        response = client.get(f"/api/v2beta/modules/{uid}", headers=admin_auth_header)

        assert response.status_code == 200
        assert response.json()["enabled"] is False
