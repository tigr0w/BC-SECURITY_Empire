def test_get_profile_not_found(client, admin_auth_header):
    response = client.get(
        "/api/v2beta/malleable-profiles/9999", headers=admin_auth_header
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Profile not found for id 9999"


def test_get_profile(client, admin_auth_header):
    response = client.get("/api/v2beta/malleable-profiles/1", headers=admin_auth_header)

    assert response.status_code == 200
    assert response.json()["id"] == 1
    assert len(response.json()["data"]) > 0


def test_get_profiles(client, admin_auth_header):
    response = client.get("/api/v2beta/malleable-profiles", headers=admin_auth_header)

    assert response.status_code == 200
    assert len(response.json()["records"]) > 0


def test_create_profile(client, admin_auth_header):
    response = client.post(
        "/api/v2beta/malleable-profiles/",
        headers=admin_auth_header,
        json={"name": "Test Profile", "category": "cat", "data": "x=0;"},
    )

    assert response.status_code == 201
    assert response.json()["name"] == "Test Profile"
    assert response.json()["category"] == "cat"
    assert response.json()["data"] == "x=0;"


def test_update_profile_not_found(client, admin_auth_header):
    response = client.put(
        "/api/v2beta/malleable-profiles/9999",
        headers=admin_auth_header,
        json={"name": "Test Profile", "category": "cat", "data": "x=0;"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Profile not found for id 9999"


def test_update_profile(client, admin_auth_header):
    response = client.put(
        "/api/v2beta/malleable-profiles/1",
        headers=admin_auth_header,
        json={"data": "x=1;"},
    )

    assert response.json()["id"] == 1
    assert response.json()["data"] == "x=1;"


def test_delete_profile(client, admin_auth_header):
    response = client.delete(
        "/api/v2beta/malleable-profiles/1", headers=admin_auth_header
    )

    assert response.status_code == 204

    response = client.get("/api/v2beta/malleable-profiles/1", headers=admin_auth_header)

    assert response.status_code == 404
