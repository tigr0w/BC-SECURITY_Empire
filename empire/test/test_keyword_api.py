def test_get_keyword_not_found(client, admin_auth_header):
    response = client.get("/api/v2beta/keywords/9999", headers=admin_auth_header)

    assert response.status_code == 404
    assert response.json()["detail"] == "Keyword not found for id 9999"


def test_get_keyword(client, admin_auth_header):
    response = client.get("/api/v2beta/keywords/1", headers=admin_auth_header)

    assert response.status_code == 200
    assert response.json()["id"] == 1
    assert len(response.json()["replacement"]) > 0


def test_get_keywords(client, admin_auth_header):
    response = client.get("/api/v2beta/keywords", headers=admin_auth_header)

    assert response.status_code == 200
    assert len(response.json()["records"]) > 0


def test_create_keyword_name_conflict(client, admin_auth_header):
    response = client.post(
        "/api/v2beta/keywords/",
        headers=admin_auth_header,
        json={"keyword": "Invoke_Mimikatz", "replacement": "Invoke-Hax"},
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"] == "Keyword with name Invoke_Mimikatz already exists."
    )


def test_create_keyword(client, admin_auth_header):
    response = client.post(
        "/api/v2beta/keywords/",
        headers=admin_auth_header,
        json={"keyword": "Invoke-Things", "replacement": "Invoke-sgnihT;"},
    )

    assert response.status_code == 201
    assert response.json()["keyword"] == "Invoke-Things"
    assert response.json()["replacement"] == "Invoke-sgnihT;"


def test_update_keyword_not_found(client, admin_auth_header):
    response = client.put(
        "/api/v2beta/keywords/9999",
        headers=admin_auth_header,
        json={"keyword": "thiswontwork", "replacement": "x=0;"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Keyword not found for id 9999"


def test_update_keyword_name_conflict(client, admin_auth_header):
    response = client.put(
        "/api/v2beta/keywords/1",
        headers=admin_auth_header,
        json={"keyword": "Invoke_Mimikatz", "replacement": "Invoke-Whatever"},
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"] == "Keyword with name Invoke_Mimikatz already exists."
    )


def test_update_keyword(client, admin_auth_header):
    response = client.put(
        "/api/v2beta/keywords/1",
        headers=admin_auth_header,
        json={"keyword": "Completely-new_name", "replacement": "qwerefdsgaf"},
    )

    assert response.json()["keyword"] == "Completely-new_name"
    assert response.json()["replacement"] == "qwerefdsgaf"


def test_delete_keyword(client, admin_auth_header):
    response = client.delete("/api/v2beta/keywords/1", headers=admin_auth_header)

    assert response.status_code == 204

    response = client.get("/api/v2beta/keywords/1", headers=admin_auth_header)

    assert response.status_code == 404
