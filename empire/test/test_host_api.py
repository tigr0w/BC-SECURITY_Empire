import pytest

from empire.server.database import models


@pytest.fixture(scope="module", autouse=True)
def host(db):
    host = models.Host(name='HOST_1',
                       internal_ip='1.1.1.1')

    host2 = models.Host(name='HOST_2',
                        internal_ip='2.2.2.2')
    db.add(host)
    db.add(host2)
    db.flush()
    db.commit()

    yield [host, host2]

    db.delete(host)
    db.delete(host2)
    db.commit()


def test_get_host_not_found(client, admin_auth_header):
    response = client.get('/api/v2beta/hosts/9999', headers=admin_auth_header)

    assert response.status_code == 404
    assert response.json()['detail'] == 'Host not found for id 9999'


def test_get_host(client, admin_auth_token, admin_auth_header):
    response = client.get('/api/v2beta/hosts/1', headers=admin_auth_header)

    assert response.status_code == 200
    assert response.json()['id'] == 1
    assert response.json()['name'] == 'HOST_1'


def test_get_hosts(client, admin_auth_header):
    response = client.get('/api/v2beta/hosts', headers=admin_auth_header)

    assert response.status_code == 200
    assert len(response.json()['records']) > 0
