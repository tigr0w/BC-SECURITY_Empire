def test_get_profile_not_found(client, admin_auth_header):
    response = client.get("/api/v2/malleable-profiles/9999", headers=admin_auth_header)

    assert response.status_code == 404
    assert response.json()["detail"] == "Profile not found for id 9999"


def test_get_profile(client, admin_auth_header):
    response = client.get("/api/v2/malleable-profiles/1", headers=admin_auth_header)

    assert response.status_code == 200
    assert response.json()["id"] == 1
    assert len(response.json()["data"]) > 0


def test_get_profiles(client, admin_auth_header):
    response = client.get("/api/v2/malleable-profiles", headers=admin_auth_header)

    assert response.status_code == 200
    assert len(response.json()["records"]) > 0


def test_create_profile(client, admin_auth_header):
    response = client.post(
        "/api/v2/malleable-profiles/",
        headers=admin_auth_header,
        json={"name": "Test Profile", "category": "cat", "data": "x=0;"},
    )

    assert response.status_code == 201
    assert response.json()["name"] == "Test Profile"
    assert response.json()["category"] == "cat"
    assert response.json()["data"] == "x=0;"


def test_update_profile_not_found(client, admin_auth_header):
    response = client.put(
        "/api/v2/malleable-profiles/9999",
        headers=admin_auth_header,
        json={"name": "Test Profile", "category": "cat", "data": "x=0;"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Profile not found for id 9999"


def test_update_profile(client, admin_auth_header):
    response = client.put(
        "/api/v2/malleable-profiles/1",
        headers=admin_auth_header,
        json={"data": "x=1;"},
    )

    assert response.json()["id"] == 1
    assert response.json()["data"] == "x=1;"


def test_delete_profile(client, admin_auth_header):
    response = client.delete("/api/v2/malleable-profiles/1", headers=admin_auth_header)

    assert response.status_code == 204

    response = client.get("/api/v2/malleable-profiles/1", headers=admin_auth_header)

    assert response.status_code == 404


def test_reset_profiles(client, admin_auth_header):
    response = client.post(
        "/api/v2/malleable-profiles/reset", headers=admin_auth_header
    )
    assert response.status_code == 204

    initial_response = client.get(
        "/api/v2/malleable-profiles", headers=admin_auth_header
    )
    initial_profiles = initial_response.json()["records"]

    response = client.post(
        "/api/v2/malleable-profiles",
        headers=admin_auth_header,
        json={"name": "Test Profile", "category": "cat", "data": "x=0;"},
    )
    assert response.status_code == 201

    response = client.post(
        "/api/v2/malleable-profiles/reset", headers=admin_auth_header
    )
    assert response.status_code == 204

    final_response = client.get("/api/v2/malleable-profiles", headers=admin_auth_header)
    final_profiles = final_response.json()["records"]

    assert len(initial_profiles) == len(final_profiles)


def test_reload_profiles(client, admin_auth_header):
    response = client.post(
        "/api/v2/malleable-profiles",
        headers=admin_auth_header,
        json={"name": "Test Profile", "category": "cat", "data": "x=0;"},
    )
    assert response.status_code == 201
    new_profile_id = response.json()["id"]

    initial_response = client.get(
        "/api/v2/malleable-profiles", headers=admin_auth_header
    )
    initial_profiles = initial_response.json()["records"]

    response = client.post(
        "/api/v2/malleable-profiles/reload", headers=admin_auth_header
    )
    assert response.status_code == 204

    final_response = client.get("/api/v2/malleable-profiles", headers=admin_auth_header)
    final_profiles = final_response.json()["records"]

    assert len(initial_profiles) == len(final_profiles)
    assert any(profile["id"] == new_profile_id for profile in final_profiles)
