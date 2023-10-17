def test_create_user(client, admin_auth_header):
    response = client.post(
        "/api/v2/users/",
        headers=admin_auth_header,
        json={"username": "another-user", "password": "hunter2", "is_admin": False},
    )

    assert response.status_code == 201
    assert response.json()["username"] == "another-user"


def test_create_user_name_conflict(client, admin_auth_header):
    response = client.post(
        "/api/v2/users/",
        headers=admin_auth_header,
        json={"username": "empireadmin", "password": "password", "is_admin": False},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "A user with name empireadmin already exists."


def test_create_user_not_an_admin(client, regular_auth_token):
    response = client.post(
        "/api/v2/users/",
        headers={"Authorization": f"Bearer {regular_auth_token}"},
        json={"username": "vinnybod2", "password": "hunter2", "admin": False},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Not an admin user"


def test_get_user_not_found(client, admin_auth_header):
    response = client.get("/api/v2/users/9999", headers=admin_auth_header)

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found for id 9999"


def test_get_user(client, admin_auth_header):
    response = client.get("/api/v2/users/1", headers=admin_auth_header)

    assert response.status_code == 200
    assert response.json()["id"] == 1
    assert response.json()["username"] == "empireadmin"


def test_get_me(client, regular_auth_token):
    response = client.get(
        "/api/v2/users/me",
        headers={"Authorization": f"Bearer {regular_auth_token}"},
    )

    assert response.status_code == 200
    assert response.json()["username"] == "vinnybod"


def test_update_user_not_found(client, admin_auth_header):
    response = client.put(
        "/api/v2/users/9999",
        headers=admin_auth_header,
        json={"username": "not-gonna-happen", "enabled": False, "is_admin": False},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found for id 9999"


def test_update_user_as_admin(client, admin_auth_header):
    response = client.put(
        "/api/v2/users/2",
        headers=admin_auth_header,
        json={"username": "empireadmin-2.0", "enabled": True, "is_admin": False},
    )

    assert response.status_code == 200
    assert response.json()["id"] == 2
    assert response.json()["username"] == "empireadmin-2.0"


def test_update_user_as_not_admin_not_me(client, regular_auth_token):
    response = client.put(
        "/api/v2/users/1",
        headers={"Authorization": f"Bearer {regular_auth_token}"},
        json={"username": "regular-user", "enabled": True, "is_admin": False},
    )

    assert response.status_code == 403
    assert (
        response.json()["detail"]
        == "User does not have access to update this resource."
    )


def test_update_user_as_not_admin_me(client, regular_auth_token):
    response = client.put(
        "/api/v2/users/3",
        headers={"Authorization": f"Bearer {regular_auth_token}"},
        json={"username": "xyz", "enabled": True, "is_admin": True},
    )

    assert response.status_code == 403
    assert (
        response.json()["detail"] == "User does not have access to update admin status."
    )


def test_update_user_password_not_me(client, regular_auth_token):
    response = client.put(
        "/api/v2/users/1/password",
        headers={"Authorization": f"Bearer {regular_auth_token}"},
        json={"password": "QWERTY"},
    )

    assert response.status_code == 403
    assert (
        response.json()["detail"]
        == "User does not have access to update this resource."
    )


def test_update_user_password(client):
    response = client.post(
        "/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "password",
            "username": "empireadmin-2.0",
            "password": "hunter2",
        },
    )

    response = client.put(
        "/api/v2/users/2/password",
        headers={"Authorization": f"Bearer {response.json()['access_token']}"},
        json={"password": "QWERTY"},
    )

    assert response.status_code == 200

    response = client.post(
        "/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "password",
            "username": "empireadmin-2.0",
            "password": "QWERTY",
        },
    )

    assert response.status_code == 200


def test_upload_user_avatar_not_me(client, regular_auth_token):
    response = client.post(
        "/api/v2/users/1/avatar",
        headers={"Authorization": f"Bearer {regular_auth_token}"},
        files={
            "file": (
                "avatar.png",
                open("./empire/test/avatar.png", "rb").read(),
            )
        },
    )

    assert response.status_code == 403
    assert (
        response.json()["detail"]
        == "User does not have access to update this resource."
    )


def test_upload_user_avatar_not_image(client, admin_auth_header):
    response = client.post(
        "/api/v2/users/1/avatar",
        headers=admin_auth_header,
        files={
            "file": (
                "test-upload.yaml",
                open("./empire/test/test-upload.yaml", "rb").read(),
            )
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "File must be an image."


def test_upload_user_avatar(client, admin_auth_header):
    response = client.post(
        "/api/v2/users/1/avatar",
        headers=admin_auth_header,
        files={
            "file": (
                "avatar.png",
                open("./empire/test/avatar.png", "rb").read(),
            )
        },
    )

    assert response.status_code == 201

    response = client.get("/api/v2/users/1", headers=admin_auth_header)

    assert response.status_code == 200

    avatar = response.json()["avatar"]
    first_avatar_id = avatar["id"]
    assert first_avatar_id > 0
    assert avatar["filename"] == "avatar.png"
    assert avatar["link"] == f"/api/v2/downloads/{first_avatar_id}/download"

    # Upload a second image to see if it replaces the first
    response = client.post(
        "/api/v2/users/1/avatar",
        headers=admin_auth_header,
        files={
            "file": (
                "avatar2.png",
                open("./empire/test/avatar2.png", "rb").read(),
            )
        },
    )

    assert response.status_code == 201

    response = client.get("/api/v2/users/1", headers=admin_auth_header)

    assert response.status_code == 200

    avatar = response.json()["avatar"]
    assert avatar["id"] != first_avatar_id
    assert avatar["filename"] == "avatar2.png"
    assert avatar["link"] == f"/api/v2/downloads/{avatar['id']}/download"
