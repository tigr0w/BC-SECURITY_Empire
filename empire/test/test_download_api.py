import urllib.parse
from pathlib import Path

import pytest
from starlette import status

from empire.server.api.v2.download.download_api import _media_type


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("launcher.txt", "text/plain"),
        ("launcher.bat", "text/plain"),
        ("launcher.ps1", "text/plain"),
        ("launcher.py", "text/plain"),
        ("launcher.sh", "text/plain"),
        ("payload.vbs", "text/plain"),
        ("payload.hta", "text/plain"),
        ("stylesheet.xsl", "text/plain"),
        ("teensy.ino", "text/plain"),
        ("sessions.csv", "text/plain"),
        ("master.log", "text/plain"),
        ("screenshot.png", "image/png"),
        ("screenshot.JPG", "image/jpeg"),
        ("avatar.jpeg", "image/jpeg"),
        ("avatar.gif", "image/gif"),
        # Unmapped extensions fall through to opaque.
        ("stager.dll", "application/octet-stream"),
        ("Sharpire.exe", "application/octet-stream"),
        ("out.zip", "application/octet-stream"),
        ("capture.pcap", "application/octet-stream"),
        ("empire", "application/octet-stream"),
        (".bashrc", "application/octet-stream"),
        ("avatar.svg", "application/octet-stream"),
    ],
)
def test_media_type_is_host_independent(filename, expected):
    assert _media_type(filename) == expected


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        # Each case must be one where Empire's map and Starlette's guess
        # DISAGREE; a case where they agree cannot fail. .py and .svg come from
        # CPython's built-in table, so they discriminate even on a host with no
        # mime file at all.
        ("guard.py", "text/plain"),  # built-in says text/x-python
        ("guard.svg", "application/octet-stream"),  # built-in says image/svg+xml
        ("guard.ps1", "text/plain"),  # unmapped, so the guess is octet-stream
    ],
)
def test_download_media_type_comes_from_empire_not_the_host(
    client, admin_auth_header, filename, expected
):
    """Drop the ``media_type=`` kwarg from the ``FileResponse`` and all three
    cases must fail - that is the regression this guards.
    """
    created = client.post(
        "/api/v2/downloads",
        headers=admin_auth_header,
        files={"file": (filename, b"guard")},
    )
    assert created.status_code == status.HTTP_201_CREATED

    response = client.get(
        f"/api/v2/downloads/{created.json()['id']}/download",
        headers=admin_auth_header,
    )

    assert response.status_code == status.HTTP_200_OK
    # Starlette appends '; charset=utf-8' to text/* types.
    assert response.headers["content-type"].split(";")[0].strip() == expected


def test_get_download_not_found(client, admin_auth_header):
    response = client.get("/api/v2/downloads/9999", headers=admin_auth_header)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Download not found for id 9999"


def test_create_download(client, admin_auth_header):
    response = client.post(
        "/api/v2/downloads",
        headers=admin_auth_header,
        files={
            "file": (
                "test-upload-2.yaml",
                Path("./empire/test/test-upload-2.yaml").read_bytes(),
            )
        },
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["id"] > 0


def test_create_download_appends_number_if_already_exists(client, admin_auth_header):
    response = client.post(
        "/api/v2/downloads",
        headers=admin_auth_header,
        files={
            "file": (
                "test-upload-2.yaml",
                Path("./empire/test/test-upload-2.yaml").read_bytes(),
            )
        },
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["id"] > 0

    response = client.post(
        "/api/v2/downloads",
        headers=admin_auth_header,
        files={
            "file": (
                "test-upload-2.yaml",
                Path("./empire/test/test-upload-2.yaml").read_bytes(),
            )
        },
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["id"] > 0
    assert response.json()["location"].endswith(").yaml")
    assert response.json()["filename"].endswith(").yaml")


def test_create_download_blocks_path_traversal(client, admin_auth_header):
    escaped = Path("/tmp/empire_download_traversal.txt")
    escaped.unlink(missing_ok=True)
    response = client.post(
        "/api/v2/downloads",
        headers=admin_auth_header,
        files={
            "file": (
                "../../../../../../../../tmp/empire_download_traversal.txt",
                b"pwned",
            )
        },
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "Invalid filename."
    assert not escaped.exists(), "traversal file escaped the downloads directory"


def test_get_download(client, admin_auth_header, download):
    response = client.get(f"/api/v2/downloads/{download}", headers=admin_auth_header)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == download
    assert "test-upload-2" in response.json()["filename"]


def test_download_download(client, admin_auth_header, download):
    response = client.get(
        f"/api/v2/downloads/{download}/download", headers=admin_auth_header
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.headers.get("content-disposition").lower().startswith(
        'attachment; filename="test-upload-2'
    ) or response.headers.get("content-disposition").lower().startswith(
        "attachment; filename*=utf-8''test-upload-2"
    )


def test_get_downloads(client, admin_auth_header):
    min_expected_downloads = 2
    response = client.get("/api/v2/downloads", headers=admin_auth_header)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["total"] > min_expected_downloads


def test_get_downloads_with_query(client, admin_auth_header):
    response = client.get(
        "/api/v2/downloads?query=gobblygook", headers=admin_auth_header
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["total"] == 0
    assert response.json()["records"] == []

    q = urllib.parse.urlencode({"query": "test-upload"})
    response = client.get(f"/api/v2/downloads?{q}", headers=admin_auth_header)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["total"] > 1
