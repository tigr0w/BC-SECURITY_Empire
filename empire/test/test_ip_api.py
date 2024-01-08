import pytest


def test_create_ip_validates(client, admin_auth_header):
    invalids = ["192.168.0.1/33", "abc-123", "192.168.0.8-192.168.0.0", "192.168.8.8.5"]

    for invalid in invalids:
        resp = client.post(
            "/api/v2/ips/",
            headers=admin_auth_header,
            json={
                "ip_address": invalid,
                "list": "allow",
            },
        )

        assert resp.status_code == 422
        assert (
            resp.json()["detail"][0]["msg"]
            == f"Value error, Invalid IP address {invalid}. Must be a valid IP Address, Range, or CIDR."
        )


def test_create_ip_allow(client, admin_auth_header):
    resp = client.post(
        "/api/v2/ips/",
        headers=admin_auth_header,
        json={
            "ip_address": "192.168.0.1",
            "list": "allow",
        },
    )

    assert resp.status_code == 201
    assert resp.json()["ip_address"] == "192.168.0.1"
    assert resp.json()["list"] == "allow"

    client.delete(
        f"/api/v2/ips/{resp.json()['id']}",
        headers=admin_auth_header,
    )


def test_create_ip_deny(client, admin_auth_header):
    resp = client.post(
        "/api/v2/ips/",
        headers=admin_auth_header,
        json={
            "ip_address": "192.168.0.1",
            "list": "deny",
        },
    )

    assert resp.status_code == 201
    assert resp.json()["ip_address"] == "192.168.0.1"
    assert resp.json()["list"] == "deny"

    client.delete(
        f"/api/v2/ips/{resp.json()['id']}",
        headers=admin_auth_header,
    )


def test_delete_ip(client, admin_auth_header):
    resp = client.post(
        "/api/v2/ips/",
        headers=admin_auth_header,
        json={
            "ip_address": "192.168.0.1",
            "list": "allow",
        },
    )

    assert resp.status_code == 201
    uid = resp.json()["id"]

    resp = client.delete(
        f"/api/v2/ips/{uid}",
        headers=admin_auth_header,
    )

    assert resp.status_code == 204

    resp = client.get(
        f"/api/v2/ips/{uid}",
        headers=admin_auth_header,
    )

    assert resp.status_code == 404


@pytest.fixture(scope="function")
def setup_ip_list(client, admin_auth_header):
    allow = ["192.168.0.1", "10.0.0.0/8", "192.168.1.0-192.168.5.0"]
    block = ["192.168.10.0"]
    for ip in allow:
        resp = client.post(
            "/api/v2/ips/",
            headers=admin_auth_header,
            json={
                "ip_address": ip,
                "list": "allow",
            },
        )

        assert resp.status_code == 201

    for ip in block:
        resp = client.post(
            "/api/v2/ips/",
            headers=admin_auth_header,
            json={
                "ip_address": ip,
                "list": "deny",
            },
        )

        assert resp.status_code == 201

    yield

    for ip in allow + block:
        client.delete(
            f"/api/v2/ips/{ip}",
            headers=admin_auth_header,
        )


def test_get_ip_list(client, admin_auth_header, setup_ip_list):
    resp = client.get(
        "/api/v2/ips/",
        headers=admin_auth_header,
    )

    assert resp.status_code == 200
    assert len(resp.json()["records"]) == 4

    resp = client.get(
        "/api/v2/ips/?ip_list=allow",
        headers=admin_auth_header,
    )

    assert resp.status_code == 200
    assert len(resp.json()["records"]) == 3
    assert all(x["list"] == "allow" for x in resp.json()["records"])

    resp = client.get(
        "/api/v2/ips/?ip_list=deny",
        headers=admin_auth_header,
    )

    assert resp.status_code == 200
    assert len(resp.json()["records"]) == 1
    assert all(x["list"] == "deny" for x in resp.json()["records"])


def test_get_ip(client, admin_auth_header):
    resp = client.post(
        "/api/v2/ips/",
        headers=admin_auth_header,
        json={
            "ip_address": "1.1.1.1",
            "list": "allow",
        },
    )

    assert resp.status_code == 201

    uid = resp.json()["id"]

    resp = client.get(
        f"/api/v2/ips/{uid}",
        headers=admin_auth_header,
    )

    assert resp.status_code == 200
    assert resp.json()["ip_address"] == "1.1.1.1"
    assert resp.json()["list"] == "allow"
