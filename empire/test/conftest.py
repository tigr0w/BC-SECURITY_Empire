import os
import sys
from pathlib import Path

import pytest

DEFAULT_ARGV = ["", "server", "--config", "empire/test/test_config.yaml"]


@pytest.fixture(scope="session", autouse=True)
def setup_args():
    os.chdir(Path(os.path.dirname(os.path.abspath(__file__))).parent.parent)
    sys.argv = DEFAULT_ARGV


@pytest.fixture(scope="session")
def default_argv():
    return DEFAULT_ARGV
