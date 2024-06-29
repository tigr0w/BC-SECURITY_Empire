import logging
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

from empire.test.conftest import SERVER_CONFIG_LOC, load_test_config


def test_simple_log_format(monkeypatch):
    logging.getLogger().handlers.clear()
    os.chdir(Path(os.path.dirname(os.path.abspath(__file__))).parent.parent)
    sys.argv = ["", "server", "--config", SERVER_CONFIG_LOC]

    monkeypatch.setattr("empire.server.server.empire", MagicMock())

    from empire import arguments
    from empire.server.server import setup_logging
    from empire.server.utils.log_util import SIMPLE_LOG_FORMAT, ColorFormatter

    args = arguments.parent_parser.parse_args()  # Force reparse of args between runs
    setup_logging(args)

    stream_handler = next(
        filter(lambda h: type(h) == logging.StreamHandler, logging.getLogger().handlers)
    )

    assert isinstance(stream_handler.formatter, ColorFormatter)
    assert stream_handler.formatter._fmt == SIMPLE_LOG_FORMAT


def test_extended_log_format(monkeypatch):
    logging.getLogger().handlers.clear()
    os.chdir(Path(os.path.dirname(os.path.abspath(__file__))).parent.parent)
    sys.argv = ["", "server", "--config", SERVER_CONFIG_LOC]

    monkeypatch.setattr("empire.server.server.empire", MagicMock())

    from empire import arguments
    from empire.server.core.config import EmpireConfig
    from empire.server.server import setup_logging
    from empire.server.utils.log_util import LOG_FORMAT, ColorFormatter

    test_config = load_test_config()
    test_config["logging"]["simple_console"] = False
    modified_config = EmpireConfig(test_config)
    monkeypatch.setattr("empire.server.server.empire_config", modified_config)

    args = arguments.parent_parser.parse_args()  # Force reparse of args between runs
    setup_logging(args)

    stream_handler = next(
        filter(lambda h: type(h) == logging.StreamHandler, logging.getLogger().handlers)
    )

    assert isinstance(stream_handler.formatter, ColorFormatter)
    assert stream_handler.formatter._fmt == LOG_FORMAT


def test_log_level_by_config(monkeypatch):
    logging.getLogger().handlers.clear()
    os.chdir(Path(os.path.dirname(os.path.abspath(__file__))).parent.parent)
    sys.argv = ["", "server", "--config", SERVER_CONFIG_LOC]

    monkeypatch.setattr("empire.server.server.empire", MagicMock())

    from empire import arguments
    from empire.server.core.config import EmpireConfig
    from empire.server.server import setup_logging

    test_config = load_test_config()
    test_config["logging"]["level"] = "WaRNiNG"  # case insensitive
    modified_config = EmpireConfig(test_config)
    monkeypatch.setattr("empire.server.server.empire_config", modified_config)

    args = arguments.parent_parser.parse_args()  # Force reparse of args between runs
    setup_logging(args)

    stream_handler = next(
        filter(lambda h: type(h) == logging.StreamHandler, logging.getLogger().handlers)
    )

    assert stream_handler.level == logging.WARNING


def test_log_level_by_arg():
    logging.getLogger().handlers.clear()
    os.chdir(Path(os.path.dirname(os.path.abspath(__file__))).parent.parent)
    sys.argv = [
        "",
        "server",
        "--config",
        SERVER_CONFIG_LOC,
        "--log-level",
        "ERROR",
    ]

    from empire import arguments
    from empire.server.server import setup_logging

    config_mock = MagicMock()
    test_config = load_test_config()
    test_config["logging"]["level"] = "WaRNiNG"  # Should be overwritten by arg
    config_mock.yaml = test_config

    args = arguments.parent_parser.parse_args()  # Force reparse of args between runs
    setup_logging(args)

    stream_handler = next(
        filter(lambda h: type(h) == logging.StreamHandler, logging.getLogger().handlers)
    )

    assert stream_handler.level == logging.ERROR


def test_log_level_by_debug_arg():
    logging.getLogger().handlers.clear()
    os.chdir(Path(os.path.dirname(os.path.abspath(__file__))).parent.parent)
    sys.argv = ["", "server", "--config", SERVER_CONFIG_LOC, "--debug"]

    from empire import arguments
    from empire.server.server import setup_logging

    config_mock = MagicMock()
    test_config = load_test_config()
    test_config["logging"]["level"] = "WaRNiNG"  # Should be overwritten by arg
    config_mock.yaml = test_config

    args = arguments.parent_parser.parse_args()  # Force reparse of args between runs
    setup_logging(args)

    assert logging.getLogger().level == logging.DEBUG


def test_log_file_not_owned_by_root(monkeypatch):
    logging.getLogger().handlers.clear()
    os.chdir(Path(os.path.dirname(os.path.abspath(__file__))).parent.parent)
    sys.argv = ["", "server", "--config", SERVER_CONFIG_LOC]

    monkeypatch.setattr("empire.server.server.empire", MagicMock())

    from empire import arguments
    from empire.server.core.config import EmpireConfig
    from empire.server.server import setup_logging

    test_config = load_test_config()
    config = EmpireConfig(test_config)
    monkeypatch.setattr("empire.server.server.empire_config", config)

    args = arguments.parent_parser.parse_args()
    setup_logging(args)

    log_dir = Path(config.logging.directory)
    log_file_path = log_dir / "empire_server.log"

    assert log_file_path.exists(), "Empire log file does not exist."

    stat_info = os.stat(log_file_path)

    assert stat_info.st_uid != 0, "Empire log file is owned by root."

    listener_log_dir = Path(config.logging.directory)
    listener_log_file_path = listener_log_dir / "listener_new-listener-1.log"

    assert listener_log_file_path.exists(), "Listener log file does not exist."

    listener_stat_info = os.stat(listener_log_file_path)

    assert listener_stat_info.st_uid != 0, "Listener log file is owned by root."
