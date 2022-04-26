import sys
from importlib import reload


def test_load_sqlite():
    import empire.server.common.config

    reload(empire.server.common.config)
    from empire.server.common.config import EmpireConfig, empire_config

    config: EmpireConfig = empire_config

    assert config.database.type == "sqlite"
    assert config.database.location == "empire/server/data/test_empire.db"


def test_load_mysql(default_argv):
    sys.argv = ["", "server", "--config", "empire/test/test_config_mysql.yaml"]
    import empire.server.common.config

    reload(empire.server.common.config)
    from empire.server.common.config import EmpireConfig, empire_config

    config: EmpireConfig = empire_config

    assert config.database.type == "mysql"
    assert config.database.url == "localhost:3306"

    # set back to sqlite for subsequent tests
    sys.argv = default_argv
    reload(empire.server.common.config)
