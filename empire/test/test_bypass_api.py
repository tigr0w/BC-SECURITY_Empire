def test_get_bypass_not_found(client, admin_auth_header):
    response = client.get("/api/v2beta/bypasses/9999", headers=admin_auth_header)

    assert response.status_code == 404
    assert response.json()["detail"] == "Bypass not found for id 9999"


def test_get_bypass(client, admin_auth_header):
    response = client.get("/api/v2beta/bypasses/1", headers=admin_auth_header)

    assert response.status_code == 200
    assert response.json()["id"] == 1
    assert len(response.json()["code"]) > 0


def test_get_bypasses(client, admin_auth_header):
    response = client.get("/api/v2beta/bypasses", headers=admin_auth_header)

    assert response.status_code == 200
    assert len(response.json()["records"]) > 0


def test_create_bypass_name_conflict(client, admin_auth_header):
    response = client.post(
        "/api/v2beta/bypasses/",
        headers=admin_auth_header,
        json={"name": "mattifestation", "code": "x=0;"},
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"] == "Bypass with name mattifestation already exists."
    )


def test_create_bypass(client, admin_auth_header):
    response = client.post(
        "/api/v2beta/bypasses/",
        headers=admin_auth_header,
        json={"name": "Test Bypass", "code": "x=0;"},
    )

    assert response.status_code == 201
    assert response.json()["name"] == "Test Bypass"
    assert response.json()["code"] == "x=0;"


def test_update_bypass_not_found(client, admin_auth_header):
    response = client.put(
        "/api/v2beta/bypasses/9999",
        headers=admin_auth_header,
        json={"name": "Test Bypass", "code": "x=0;"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Bypass not found for id 9999"


def test_update_bypass_name_conflict(client, admin_auth_header):
    response = client.get("/api/v2beta/bypasses/1", headers=admin_auth_header)
    bypass_1_name = response.json()["name"]

    response = client.put(
        f"/api/v2beta/bypasses/5",
        headers=admin_auth_header,
        json={"name": bypass_1_name, "code": "x=0;"},
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"] == f"Bypass with name {bypass_1_name} already exists."
    )


def test_update_bypass(client, admin_auth_header):
    response = client.put(
        "/api/v2beta/bypasses/1",
        headers=admin_auth_header,
        json={"name": "Updated Bypass", "code": "x=1;"},
    )

    assert response.json()["name"] == "Updated Bypass"
    assert response.json()["code"] == "x=1;"


def test_delete_bypass(client, admin_auth_header):
    response = client.delete("/api/v2beta/bypasses/1", headers=admin_auth_header)

    assert response.status_code == 204

    response = client.get("/api/v2beta/bypasses/1", headers=admin_auth_header)

    assert response.status_code == 404
