import pytest


@pytest.fixture(scope="module", autouse=True)
def host(db, models):
    host = models.Host(name="HOST_1", internal_ip="1.1.1.1")
    host2 = models.Host(name="HOST_2", internal_ip="2.2.2.2")

    db.add(host)
    db.add(host2)
    db.commit()

    yield [host, host2]

    db.delete(host)
    db.delete(host2)
    db.commit()


def test_get_host_not_found(client, admin_auth_header):
    response = client.get("/api/v2/hosts/9999", headers=admin_auth_header)

    assert response.status_code == 404
    assert response.json()["detail"] == "Host not found for id 9999"


def test_get_host(client, host, admin_auth_token, admin_auth_header):
    response = client.get(f"/api/v2/hosts/{host[0].id}", headers=admin_auth_header)

    assert response.status_code == 200
    assert response.json()["id"] == host[0].id
    assert response.json()["name"] == host[0].name


def test_get_hosts(client, admin_auth_header):
    response = client.get("/api/v2/hosts", headers=admin_auth_header)

    assert response.status_code == 200
    assert len(response.json()["records"]) > 0
