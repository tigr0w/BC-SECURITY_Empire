import os
import sys
from pathlib import Path

import pytest

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
