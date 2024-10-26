from pathlib import Path

import pytest

from empire.server.core.config import EmpireConfig
from empire.test.conftest import load_test_config


def test_config_resolves_path():
    server_config_dict = load_test_config()
    server_config_dict["directories"]["downloads"] = "~/.empire/server/downloads"
    empire_config = EmpireConfig(server_config_dict)
    assert isinstance(empire_config.directories.downloads, Path)
    assert not str(empire_config.directories.downloads).startswith("~")


def test_config_validates_registry_location_or_url():
    server_config_dict = load_test_config()

    server_config_dict["plugin_registries"][0]["location"] = None
    server_config_dict["plugin_registries"][0]["url"] = None

    with pytest.raises(ValueError, match="Either location or url must be set"):
        EmpireConfig(server_config_dict)
