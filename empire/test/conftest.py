import os
import shutil
import sys
from importlib import reload
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

SERVER_CONFIG_LOC = "empire/test/test_server_config.yaml"
CLIENT_CONFIG_LOC = "empire/test/test_client_config.yaml"
DEFAULT_ARGV = ["", "server", "--config", SERVER_CONFIG_LOC]


@pytest.fixture(scope="session", autouse=True)
def setup_args():
    os.chdir(Path(os.path.dirname(os.path.abspath(__file__))).parent.parent)
    sys.argv = DEFAULT_ARGV


@pytest.fixture(scope="session")
def default_argv():
    return DEFAULT_ARGV


@pytest.fixture(scope="session")
def client(empire_config):
    os.chdir(Path(os.path.dirname(os.path.abspath(__file__))).parent.parent)

    import empire.server.core.db.base
    from empire.server.core.db.base import reset_db

    reset_db()
    reload(empire.server.core.db.base)

    shutil.rmtree("empire/test/downloads", ignore_errors=True)
    shutil.rmtree("empire/test/data/obfuscated_module_source", ignore_errors=True)

    sys.argv = ["", "server", "--config", SERVER_CONFIG_LOC]

    from empire import arguments

    args = arguments.parent_parser.parse_args()

    import empire.server.server
    from empire.server.common.empire import MainMenu

    empire.server.server.main = MainMenu(args)

    from empire.server.api.v2.agent import agent_api, agent_file_api, agent_task_api
    from empire.server.api.v2.bypass import bypass_api
    from empire.server.api.v2.credential import credential_api
    from empire.server.api.v2.download import download_api
    from empire.server.api.v2.host import host_api, process_api
    from empire.server.api.v2.listener import listener_api, listener_template_api
    from empire.server.api.v2.meta import meta_api
    from empire.server.api.v2.module import module_api
    from empire.server.api.v2.obfuscation import obfuscation_api
    from empire.server.api.v2.plugin import plugin_api
    from empire.server.api.v2.profile import profile_api
    from empire.server.api.v2.stager import stager_api, stager_template_api
    from empire.server.api.v2.user import user_api

    v2App = FastAPI()
    v2App.include_router(listener_template_api.router)
    v2App.include_router(listener_api.router)
    v2App.include_router(stager_template_api.router)
    v2App.include_router(stager_api.router)
    v2App.include_router(agent_task_api.router)
    v2App.include_router(agent_file_api.router)
    v2App.include_router(agent_api.router)
    v2App.include_router(module_api.router)
    v2App.include_router(bypass_api.router)
    v2App.include_router(obfuscation_api.router)
    v2App.include_router(profile_api.router)
    v2App.include_router(plugin_api.router)
    v2App.include_router(credential_api.router)
    v2App.include_router(host_api.router)
    v2App.include_router(user_api.router)
    v2App.include_router(process_api.router)
    v2App.include_router(download_api.router)
    v2App.include_router(meta_api.router)

    yield TestClient(v2App)

    print("cleanup")

    from empire.server.core.db.base import engine
    from empire.server.core.db.models import Base
    from empire.server.server import main

    main.shutdown()
    Base.metadata.drop_all(engine)


# It would be nice to swap out the db within pytest using params.
# @pytest.fixture(scope="session", params=["mysql", "sqlite"])
@pytest.fixture(scope="session")
def empire_config():
    from empire.server.core.config import empire_config

    # This could be used to dynamically change the db location if we ever try to
    # run multiple tests in parallel.
    # random_string = "".join(random.choice(string.ascii_letters) for x in range(5))
    # empire_config.database.location = f"empire/test/test_empire_{random_string}.db"

    yield empire_config


@pytest.fixture(scope="session")
def models():
    from empire.server.core.db import models

    yield models


@pytest.fixture(scope="session")
def admin_auth_token(client):
    response = client.post(
        "/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "password",
            "username": "empireadmin",
            "password": "password123",
        },
    )

    yield response.json()["access_token"]


@pytest.fixture(scope="session")
def admin_auth_header(admin_auth_token):
    return {"Authorization": f"Bearer {admin_auth_token}"}


@pytest.fixture(scope="session")
def regular_auth_token(client, admin_auth_token):
    client.post(
        "/api/v2/users/",
        headers={"Authorization": f"Bearer {admin_auth_token}"},
        json={"username": "vinnybod", "password": "hunter2", "is_admin": False},
    )

    response = client.post(
        "/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "password", "username": "vinnybod", "password": "hunter2"},
    )

    yield response.json()["access_token"]


@pytest.fixture(scope="module")
def db():
    from empire.server.core.db.base import SessionLocal

    yield SessionLocal()


@pytest.fixture(scope="session")
def main():
    from empire.server.server import main

    yield main


@pytest.fixture(scope="function")
def base_listener():
    return {
        "name": "new-listener-1",
        "template": "http",
        "options": {
            "Name": "new-listener-1",
            "Host": "http://localhost:1336",
            "BindIP": "0.0.0.0",
            "Port": "1336",
            "Launcher": "powershell -noP -sta -w 1 -enc ",
            "StagingKey": "2c103f2c4ed1e59c0b4e2e01821770fa",
            "DefaultDelay": "5",
            "DefaultJitter": "0.0",
            "DefaultLostLimit": "60",
            "DefaultProfile": "/admin/get.php,/news.php,/login/process.php|Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; rv:11.0) like Gecko",
            "CertPath": "",
            "KillDate": "",
            "WorkingHours": "",
            "Headers": "Server:Microsoft-IIS/7.5",
            "Cookie": "",
            "StagerURI": "",
            "UserAgent": "default",
            "Proxy": "default",
            "ProxyCreds": "default",
            "SlackURL": "",
            "JA3_Evasion": "False",
        },
    }


def base_listener_non_fixture():
    return {
        "name": "new-listener-1",
        "template": "http",
        "options": {
            "Name": "new-listener-1",
            "Host": "http://localhost:1336",
            "BindIP": "0.0.0.0",
            "Port": "1336",
            "Launcher": "powershell -noP -sta -w 1 -enc ",
            "StagingKey": "2c103f2c4ed1e59c0b4e2e01821770fa",
            "DefaultDelay": "5",
            "DefaultJitter": "0.0",
            "DefaultLostLimit": "60",
            "DefaultProfile": "/admin/get.php,/news.php,/login/process.php|Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; rv:11.0) like Gecko",
            "CertPath": "",
            "KillDate": "",
            "WorkingHours": "",
            "Headers": "Server:Microsoft-IIS/7.5",
            "Cookie": "",
            "StagerURI": "",
            "UserAgent": "default",
            "Proxy": "default",
            "ProxyCreds": "default",
            "SlackURL": "",
            "JA3_Evasion": "False",
        },
    }


@pytest.fixture(scope="function")
def base_stager():
    return {
        "name": "MyStager",
        "template": "multi_launcher",
        "options": {
            "Listener": "new-listener-1",
            "Language": "powershell",
            "StagerRetries": "0",
            "OutFile": "",
            "Base64": "True",
            "Obfuscate": "False",
            "ObfuscateCommand": "Token\\All\\1",
            "SafeChecks": "True",
            "UserAgent": "default",
            "Proxy": "default",
            "ProxyCreds": "default",
            "Bypasses": "mattifestation etw",
        },
    }


@pytest.fixture(scope="function")
def base_stager_2():
    return {
        "name": "MyStager2",
        "template": "windows_dll",
        "options": {
            "Listener": "new-listener-1",
            "Language": "powershell",
            "StagerRetries": "0",
            "Arch": "x86",
            "OutFile": "my-windows-dll.dll",
            "Base64": "True",
            "Obfuscate": "False",
            "ObfuscateCommand": "Token\\All\\1",
            "SafeChecks": "True",
            "UserAgent": "default",
            "Proxy": "default",
            "ProxyCreds": "default",
            "Bypasses": "mattifestation etw",
        },
    }


@pytest.fixture(scope="session")
def server_config_dict():
    # load the config file
    import yaml

    with open(SERVER_CONFIG_LOC, "r") as f:
        config_dict = yaml.safe_load(f)

    yield config_dict


@pytest.fixture(scope="session")
def client_config_dict():
    import yaml

    with open(CLIENT_CONFIG_LOC, "r") as f:
        config_dict = yaml.safe_load(f)

    yield config_dict
