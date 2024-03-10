def test_openapi(client):
    response = client.get("/openapi.json")
    print(response.json())
    assert response.status_code == 200
    assert response.json()["openapi"] == "3.1.0"
