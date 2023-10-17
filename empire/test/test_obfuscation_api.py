import os
from contextlib import contextmanager

import pytest


@contextmanager
def patch_config(empire_config):
    """
    Change the module_source directory temporarily.
    This way preobfuscate tests don't preobfuscate hundreds of modules.
    """
    orig_src_dir = empire_config.directories.module_source
    try:
        empire_config.directories.module_source = "empire/test/data/module_source/"
        yield empire_config
    finally:
        empire_config.directories.module_source = orig_src_dir


def test_get_keyword_not_found(client, admin_auth_header):
    response = client.get(
        "/api/v2/obfuscation/keywords/9999", headers=admin_auth_header
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Keyword not found for id 9999"


def test_get_keyword(client, admin_auth_header):
    response = client.get("/api/v2/obfuscation/keywords/1", headers=admin_auth_header)

    assert response.status_code == 200
    assert response.json()["id"] == 1
    assert len(response.json()["replacement"]) > 0


def test_get_keywords(client, admin_auth_header):
    response = client.get("/api/v2/obfuscation/keywords", headers=admin_auth_header)

    assert response.status_code == 200
    assert len(response.json()["records"]) > 0


def test_create_keyword_name_conflict(client, admin_auth_header):
    response = client.post(
        "/api/v2/obfuscation/keywords/",
        headers=admin_auth_header,
        json={"keyword": "Invoke-Mimikatz", "replacement": "Invoke-Hax"},
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"] == "Keyword with name Invoke-Mimikatz already exists."
    )


def test_create_keyword_validate_length(client, admin_auth_header):
    response = client.post(
        "/api/v2/obfuscation/keywords/",
        headers=admin_auth_header,
        json={"keyword": "a", "replacement": "b"},
    )

    assert response.status_code == 422
    assert (
        response.json()["detail"][0]["msg"]
        == "ensure this value has at least 3 characters"
    )


def test_create_keyword(client, admin_auth_header):
    response = client.post(
        "/api/v2/obfuscation/keywords/",
        headers=admin_auth_header,
        json={"keyword": "Invoke-Things", "replacement": "Invoke-sgnihT;"},
    )

    assert response.status_code == 201
    assert response.json()["keyword"] == "Invoke-Things"
    assert response.json()["replacement"] == "Invoke-sgnihT;"


def test_update_keyword_not_found(client, admin_auth_header):
    response = client.put(
        "/api/v2/obfuscation/keywords/9999",
        headers=admin_auth_header,
        json={"keyword": "thiswontwork", "replacement": "x=0;"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Keyword not found for id 9999"


def test_update_keyword_name_conflict(client, admin_auth_header):
    response = client.put(
        "/api/v2/obfuscation/keywords/1",
        headers=admin_auth_header,
        json={"keyword": "Invoke-Mimikatz", "replacement": "Invoke-Whatever"},
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"] == "Keyword with name Invoke-Mimikatz already exists."
    )


def test_update_keyword(client, admin_auth_header):
    response = client.put(
        "/api/v2/obfuscation/keywords/1",
        headers=admin_auth_header,
        json={"keyword": "Completely-new_name", "replacement": "qwerefdsgaf"},
    )

    assert response.json()["keyword"] == "Completely-new_name"
    assert response.json()["replacement"] == "qwerefdsgaf"


def test_delete_keyword(client, admin_auth_header):
    response = client.delete(
        "/api/v2/obfuscation/keywords/1", headers=admin_auth_header
    )

    assert response.status_code == 204

    response = client.get("/api/v2/obfuscation/keywords/1", headers=admin_auth_header)

    assert response.status_code == 404


def test_get_obfuscation_configs(client, admin_auth_header):
    response = client.get("/api/v2/obfuscation/global", headers=admin_auth_header)

    assert response.status_code == 200
    assert len(response.json()["records"]) > 1

    assert any(x["language"] == "powershell" for x in response.json()["records"])
    assert any(x["language"] == "csharp" for x in response.json()["records"])
    assert any(x["language"] == "python" for x in response.json()["records"])


def test_get_obfuscation_config_not_found(client, admin_auth_header):
    response = client.get(
        "/api/v2/obfuscation/global/madeup", headers=admin_auth_header
    )

    assert response.status_code == 404
    assert (
        response.json()["detail"]
        == "Obfuscation config not found for language madeup. Only powershell is supported."
    )


def test_get_obfuscation_config(client, admin_auth_header):
    response = client.get(
        "/api/v2/obfuscation/global/powershell", headers=admin_auth_header
    )

    assert response.status_code == 200
    assert response.json()["language"] == "powershell"
    assert response.json()["enabled"] is False
    assert response.json()["command"] == r"Token\All\1"
    assert response.json()["module"] == "invoke-obfuscation"


def test_update_obfuscation_config_not_found(client, admin_auth_header):
    response = client.put(
        "/api/v2/obfuscation/global/madeup",
        headers=admin_auth_header,
        json={
            "language": "powershell",
            "command": "x=1;",
            "module": "x=1;",
            "enabled": True,
        },
    )

    assert response.status_code == 404
    assert (
        response.json()["detail"]
        == "Obfuscation config not found for language madeup. Only powershell is supported."
    )


def test_update_obfuscation_config(client, admin_auth_header):
    response = client.put(
        "/api/v2/obfuscation/global/powershell",
        headers=admin_auth_header,
        json={
            "language": "powershell",
            "command": r"Token\All\1",
            "module": "invoke-obfuscation",
            "enabled": True,
        },
    )

    assert response.json()["language"] == "powershell"
    assert response.json()["command"] == r"Token\All\1"
    assert response.json()["module"] == "invoke-obfuscation"
    assert response.json()["enabled"] is True


def test_preobfuscate_post_not_preobfuscatable(
    client, admin_auth_header, empire_config
):
    response = client.post(
        "/api/v2/obfuscation/global/csharp/preobfuscate", headers=admin_auth_header
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "Obfuscation language csharp is not preobfuscatable."
    )


@pytest.mark.slow
def test_preobfuscate_post(client, admin_auth_header, empire_config):
    with patch_config(empire_config):
        response = client.post(
            "/api/v2/obfuscation/global/powershell/preobfuscate",
            headers=admin_auth_header,
        )

        # It is run as a background task, but in tests it runs synchronously.
        assert response.status_code == 202

        module_dir = empire_config.directories.module_source
        obf_module_dir = empire_config.directories.obfuscated_module_source

        count = 0
        for root, _dirs, files in os.walk(module_dir):
            for file in files:
                root_rep = root.replace(module_dir, obf_module_dir)
                assert os.path.exists(root_rep + "/" + file)
                count += 1

        assert count > 0


def test_preobfuscate_delete_not_preobfuscatable(
    client, admin_auth_header, empire_config
):
    response = client.delete(
        "/api/v2/obfuscation/global/csharp/preobfuscate", headers=admin_auth_header
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "Obfuscation language csharp is not preobfuscatable."
    )


def test_preobfuscate_delete(client, admin_auth_header, empire_config):
    with patch_config(empire_config):
        response = client.delete(
            "/api/v2/obfuscation/global/powershell/preobfuscate",
            headers=admin_auth_header,
        )

        assert response.status_code == 204

        module_dir = empire_config.directories.module_source
        obf_module_dir = empire_config.directories.obfuscated_module_source

        for root, _dirs, files in os.walk(module_dir):
            for file in files:
                root_rep = root.replace(module_dir, obf_module_dir)
                assert not os.path.exists(root_rep + "/" + file)
