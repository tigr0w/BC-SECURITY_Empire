import urllib.parse

download_id = None


def test_get_download_not_found(client, admin_auth_header):
    response = client.get("/api/v2/downloads/9999", headers=admin_auth_header)

    assert response.status_code == 404
    assert response.json()["detail"] == "Download not found for id 9999"


def test_create_download(client, admin_auth_header):
    response = client.post(
        "/api/v2/downloads",
        headers=admin_auth_header,
        files={
            "file": (
                "test-upload-2.yaml",
                open("./empire/test/test-upload-2.yaml").read(),
            )
        },
    )

    assert response.status_code == 201
    global download_id
    download_id = response.json()["id"]


def test_create_download_appends_number_if_already_exists(client, admin_auth_header):
    response = client.post(
        "/api/v2/downloads",
        headers=admin_auth_header,
        files={
            "file": (
                "test-upload-2.yaml",
                open("./empire/test/test-upload-2.yaml").read(),
            )
        },
    )

    assert response.status_code == 201
    assert response.json()["id"] > 0

    response = client.post(
        "/api/v2/downloads",
        headers=admin_auth_header,
        files={
            "file": (
                "test-upload-2.yaml",
                open("./empire/test/test-upload-2.yaml").read(),
            )
        },
    )

    assert response.status_code == 201
    assert response.json()["id"] > 0
    assert response.json()["location"].endswith(").yaml")
    assert response.json()["filename"].endswith(").yaml")


def test_get_download(client, admin_auth_header):
    response = client.get(f"/api/v2/downloads/{download_id}", headers=admin_auth_header)

    assert response.status_code == 200
    assert response.json()["id"] == download_id
    assert "test-upload-2" in response.json()["filename"]


def test_download_download(client, admin_auth_header):
    response = client.get(
        f"/api/v2/downloads/{download_id}/download", headers=admin_auth_header
    )

    assert response.status_code == 200
    assert response.headers.get("content-disposition").lower().startswith(
        'attachment; filename="test-upload-2'
    ) or response.headers.get("content-disposition").lower().startswith(
        "attachment; filename*=utf-8''test-upload-2"
    )


def test_get_downloads(client, admin_auth_header):
    response = client.get("/api/v2/downloads", headers=admin_auth_header)

    assert response.status_code == 200
    assert response.json()["total"] > 2


def test_get_downloads_with_query(client, admin_auth_header):
    response = client.get(
        "/api/v2/downloads?query=gobblygook", headers=admin_auth_header
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert response.json()["records"] == []

    q = urllib.parse.urlencode({"query": "test-upload"})
    response = client.get(f"/api/v2/downloads?{q}", headers=admin_auth_header)

    assert response.status_code == 200
    assert response.json()["total"] > 1
