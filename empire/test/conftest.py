import sys

import pytest


@pytest.fixture(scope="session", autouse=True)
def setup_args():
    sys.argv = ["", "server", "--config", "empire/test/test_config.yaml"]
