import os
import random
import shutil
import string
import sys
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
    if os.path.exists("empire/test/test_empire.db"):
        os.remove("empire/test/test_empire.db")
    shutil.rmtree("empire/test/downloads", ignore_errors=True)
    shutil.rmtree("empire/test/data/obfuscated_module_source", ignore_errors=True)

    sys.argv = ["", "server", "--config", SERVER_CONFIG_LOC]

    from empire import arguments

    args = arguments.parent_parser.parse_args()

    import empire.server.server
    from empire.server.common.empire import MainMenu

    # todo vr could this weirdness be avoided if we make main menu an injected dependency for fastapi?
    empire.server.server.main = MainMenu(args)

    from empire.server.v2.api.agent import agentfilev2, agentv2, taskv2
    from empire.server.v2.api.bypass import bypassv2
    from empire.server.v2.api.credential import credentialv2
    from empire.server.v2.api.download import downloadv2
    from empire.server.v2.api.host import hostv2, processv2
    from empire.server.v2.api.listener import listenertemplatev2, listenerv2
    from empire.server.v2.api.meta import metav2
    from empire.server.v2.api.module import modulev2
    from empire.server.v2.api.obfuscation import obfuscationv2
    from empire.server.v2.api.plugin import pluginv2
    from empire.server.v2.api.profile import profilev2
    from empire.server.v2.api.stager import stagertemplatev2, stagerv2
    from empire.server.v2.api.user import userv2

    v2App = FastAPI()
    v2App.include_router(listenertemplatev2.router)
    v2App.include_router(listenerv2.router)
    v2App.include_router(stagertemplatev2.router)
    v2App.include_router(stagerv2.router)
    v2App.include_router(taskv2.router)
    v2App.include_router(agentfilev2.router)
    v2App.include_router(agentv2.router)
    v2App.include_router(modulev2.router)
    v2App.include_router(bypassv2.router)
    v2App.include_router(obfuscationv2.router)
    v2App.include_router(profilev2.router)
    v2App.include_router(pluginv2.router)
    v2App.include_router(credentialv2.router)
    v2App.include_router(hostv2.router)
    v2App.include_router(userv2.router)
    v2App.include_router(processv2.router)
    v2App.include_router(downloadv2.router)
    v2App.include_router(metav2.router)

    yield TestClient(v2App)

    print("cleanup")

    from empire.server.database.base import engine
    from empire.server.database.models import Base
    from empire.server.server import main

    main.shutdown()
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="session")
def empire_config():
    from empire.server.common.config import empire_config

    # This could be used to dynamically change the db location if we ever try to
    # run multiple tests in parallel.
    # random_string = "".join(random.choice(string.ascii_letters) for x in range(5))
    # empire_config.database.location = f"empire/test/test_empire_{random_string}.db"

    return empire_config


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
        "/api/v2beta/users/",
        headers={"Authorization": f"Bearer {admin_auth_token}"},
        json={"username": "vinnybod", "password": "hunter2", "is_admin": False},
    )

    response = client.post(
        "/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "password", "username": "vinnybod", "password": "hunter2"},
    )

    yield response.json()["access_token"]


@pytest.fixture(scope="session")
def db():
    from empire.server.database.base import SessionLocal

    yield SessionLocal()


@pytest.fixture(scope="session")
def main_menu():
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
