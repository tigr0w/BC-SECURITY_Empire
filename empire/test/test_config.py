from pathlib import Path

import pytest

from empire.server.core.config.config_manager import EmpireConfig
from empire.test.conftest import load_test_config


def test_config_resolves_path():
    server_config_dict = load_test_config()
    server_config_dict["directories"]["downloads"] = "~/.empire/server/downloads"
    empire_config = EmpireConfig(server_config_dict)
    assert isinstance(empire_config.directories.downloads, Path)
    assert not str(empire_config.directories.downloads).startswith("~")
    assert empire_config.directories.downloads.is_absolute()

    server_config_dict["directories"]["downloads"] = "/tmp/empire"
    empire_config = EmpireConfig(server_config_dict)
    assert isinstance(empire_config.directories.downloads, Path)
    assert (str(empire_config.directories.downloads).startswith("/private/tmp")) or (
        str(empire_config.directories.downloads).startswith("/tmp")
    )
    assert empire_config.directories.downloads.is_absolute()

    server_config_dict["directories"]["downloads"] = "empire/test"
    empire_config = EmpireConfig(server_config_dict)
    assert isinstance(empire_config.directories.downloads, Path)
    assert str(empire_config.directories.downloads).endswith(
        ".local/share/empire-test/empire/test"
    )
    assert empire_config.directories.downloads.is_absolute()


def test_config_validates_registry_location_or_url():
    server_config_dict = load_test_config()

    server_config_dict["plugin_marketplace"]["registries"][0]["location"] = None
    server_config_dict["plugin_marketplace"]["registries"][0]["url"] = None

    with pytest.raises(
        ValueError, match="Either location, url, or git_url must be set"
    ):
        EmpireConfig(server_config_dict)
