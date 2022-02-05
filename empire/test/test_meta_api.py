def test_version(client, admin_auth_header):
    response = client.get("/api/v2beta/meta/version", headers=admin_auth_header)

    assert response.status_code == 200
    assert (
        response.json()["version"] == "5.0.0-alpha1"
    )  # todo move version to a constant that can be imported by the tests and the server
