def test_create_user(client, admin_auth_header):
    response = client.post(
        '/api/v2beta/users/',
        headers=admin_auth_header,
        json={
            'username': 'another-user',
            'password': 'hunter2',
            'is_admin': False
        })

    assert response.status_code == 201
    assert response.json()['username'] == 'another-user'


def test_create_user_name_conflict(client, admin_auth_header):
    response = client.post(
        '/api/v2beta/users/',
        headers=admin_auth_header,
        json={
            'username': 'empireadmin',
            'password': 'password',
            'is_admin': False
        })

    assert response.status_code == 400
    assert response.json()['detail'] == 'A user with name empireadmin already exists.'


def test_create_user_not_an_admin(client, regular_auth_token):
    response = client.post(
        '/api/v2beta/users/',
        headers={'Authorization': f'Bearer {regular_auth_token}'},
        json={
            'username': 'vinnybod2',
            'password': 'hunter2',
            'admin': False
        })

    assert response.status_code == 403
    assert response.json()['detail'] == 'Not an admin user'


def test_get_user_not_found(client, admin_auth_header):
    response = client.get('/api/v2beta/users/9999', headers=admin_auth_header)

    assert response.status_code == 404
    assert response.json()['detail'] == 'User not found for id 9999'


def test_get_user(client, admin_auth_header):
    response = client.get('/api/v2beta/users/1', headers=admin_auth_header)

    assert response.status_code == 200
    assert response.json()['id'] == 1
    assert response.json()['username'] == 'empireadmin'


def test_get_me(client, regular_auth_token):
    response = client.get('/api/v2beta/users/2', headers={'Authorization': f'Bearer {regular_auth_token}'})

    assert response.status_code == 200
    assert response.json()['id'] == 2
    assert response.json()['username'] == 'vinnybod'


def test_update_user_not_found(client, admin_auth_header):
    response = client.put(
        '/api/v2beta/users/9999',
        headers=admin_auth_header,
        json={
            'username': 'not-gonna-happen',
            'enabled': False,
            'is_admin': False
        })

    assert response.status_code == 404
    assert response.json()['detail'] == 'User not found for id 9999'


# todo ensure there is always 1 admin? Ensure there is always 1 active?
#  can easily do this by just not allowing self edits?
def test_update_user_as_admin(client, admin_auth_header):
    response = client.put(
        '/api/v2beta/users/1',
        headers=admin_auth_header,
        json={
            'username': 'empireadmin-2.0',
            'enabled': True,
            'is_admin': True
        })

    assert response.status_code == 200
    assert response.json()['id'] == 1
    assert response.json()['username'] == 'empireadmin-2.0'


def test_update_user_as_not_admin_not_me(client, regular_auth_token):
    response = client.put(
        '/api/v2beta/users/1',
        headers={'Authorization': f'Bearer {regular_auth_token}'},
        json={
            'username': 'regular-user',
            'enabled': True,
            'is_admin': False
        })

    assert response.status_code == 403
    assert response.json()['detail'] == 'User does not have access to update this resource.'


def test_update_user_as_not_admin_me(client, regular_auth_token):
    response = client.put(
        '/api/v2beta/users/2',
        headers={'Authorization': f'Bearer {regular_auth_token}'},
        json={
            'username': 'xyz',
            'enabled': True,
            'is_admin': True
        })

    assert response.status_code == 403
    assert response.json()['detail'] == 'User does not have access to update admin status.'


def test_update_user_password_not_me(client, regular_auth_token):
    response = client.put(
        '/api/v2beta/users/1/password',
        headers={'Authorization': f'Bearer {regular_auth_token}'},
        json={'password': 'QWERTY'})

    assert response.status_code == 403
    assert response.json()['detail'] == "User does not have access to update this resource."


# todo shouldn't mess with the admin user because it will mess up the fixtures. meh.
def test_update_user_password(client, admin_auth_header):
    response = client.put(
        '/api/v2beta/users/1/password',
        headers=admin_auth_header,
        json={'password': 'QWERTY'})

    assert response.status_code == 200

    response = client.post(
        '/token',
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        data={
            'grant_type': 'password',
            'username': 'empireadmin',
            'password': 'QWERTY'
        })

    assert response.status_code == 200
