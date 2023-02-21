def test_version(client, admin_auth_header):
    import empire.server.common.empire

    response = client.get("/api/v2/meta/version", headers=admin_auth_header)
    assert response.status_code == 200
    assert (
        response.json()["version"] == empire.server.common.empire.VERSION.split(" ")[0]
    )
