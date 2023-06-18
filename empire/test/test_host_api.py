def test_get_host_not_found(client, admin_auth_header):
    response = client.get("/api/v2/hosts/9999", headers=admin_auth_header)

    assert response.status_code == 404
    assert response.json()["detail"] == "Host not found for id 9999"


def test_get_host(client, host, admin_auth_token, admin_auth_header):
    response = client.get(f"/api/v2/hosts/{host}", headers=admin_auth_header)

    assert response.status_code == 200
    assert response.json()["id"] == host


def test_get_hosts(client, host, admin_auth_header):
    response = client.get("/api/v2/hosts", headers=admin_auth_header)

    assert response.status_code == 200
    assert len(response.json()["records"]) > 0
