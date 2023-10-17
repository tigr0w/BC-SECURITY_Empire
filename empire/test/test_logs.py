import logging
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import yaml

from empire.test.conftest import SERVER_CONFIG_LOC


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

    assert type(stream_handler.formatter) == ColorFormatter
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

    test_config = _load_test_config()
    test_config["logging"]["simple_console"] = False
    modified_config = EmpireConfig(test_config)
    monkeypatch.setattr("empire.server.server.empire_config", modified_config)

    args = arguments.parent_parser.parse_args()  # Force reparse of args between runs
    setup_logging(args)

    stream_handler = next(
        filter(lambda h: type(h) == logging.StreamHandler, logging.getLogger().handlers)
    )

    assert type(stream_handler.formatter) == ColorFormatter
    assert stream_handler.formatter._fmt == LOG_FORMAT


def test_log_level_by_config(monkeypatch):
    logging.getLogger().handlers.clear()
    os.chdir(Path(os.path.dirname(os.path.abspath(__file__))).parent.parent)
    sys.argv = ["", "server", "--config", SERVER_CONFIG_LOC]

    monkeypatch.setattr("empire.server.server.empire", MagicMock())

    from empire import arguments
    from empire.server.core.config import EmpireConfig
    from empire.server.server import setup_logging

    test_config = _load_test_config()
    test_config["logging"]["level"] = "WaRNiNG"  # case insensitive
    modified_config = EmpireConfig(test_config)
    monkeypatch.setattr("empire.server.server.empire_config", modified_config)

    args = arguments.parent_parser.parse_args()  # Force reparse of args between runs
    setup_logging(args)

    stream_handler = next(
        filter(lambda h: type(h) == logging.StreamHandler, logging.getLogger().handlers)
    )

    assert stream_handler.level == logging.WARNING


def test_log_level_by_arg(monkeypatch):
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

    monkeypatch.setattr("empire.server.server.empire", MagicMock())

    from empire import arguments
    from empire.server.server import setup_logging

    config_mock = MagicMock()
    test_config = _load_test_config()
    test_config["logging"]["level"] = "WaRNiNG"  # Should be overwritten by arg
    config_mock.yaml = test_config
    monkeypatch.setattr("empire.server.server.empire_config", config_mock)

    args = arguments.parent_parser.parse_args()  # Force reparse of args between runs
    setup_logging(args)

    stream_handler = next(
        filter(lambda h: type(h) == logging.StreamHandler, logging.getLogger().handlers)
    )

    assert stream_handler.level == logging.ERROR


def test_log_level_by_debug_arg(monkeypatch):
    logging.getLogger().handlers.clear()
    os.chdir(Path(os.path.dirname(os.path.abspath(__file__))).parent.parent)
    sys.argv = ["", "server", "--config", SERVER_CONFIG_LOC, "--debug"]

    monkeypatch.setattr("empire.server.server.empire", MagicMock())

    from empire import arguments
    from empire.server.server import setup_logging

    config_mock = MagicMock()
    test_config = _load_test_config()
    test_config["logging"]["level"] = "WaRNiNG"  # Should be overwritten by arg
    config_mock.yaml = test_config
    monkeypatch.setattr("empire.server.server.empire_config", config_mock)

    args = arguments.parent_parser.parse_args()  # Force reparse of args between runs
    setup_logging(args)

    assert logging.getLogger().level == logging.DEBUG


def _load_test_config():
    with open(SERVER_CONFIG_LOC) as f:
        loaded = yaml.safe_load(f)
    return loaded
