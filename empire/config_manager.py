import logging
import os
import shutil
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

user_home = Path.home()
SOURCE_CONFIG_CLIENT = Path("empire/client/config.yaml")
SOURCE_CONFIG_SERVER = Path("empire/server/config.yaml")
CONFIG_DIR = user_home / ".empire"
CONFIG_SERVER_PATH = CONFIG_DIR / "server" / "config.yaml"


def config_init():
    CONFIG_SERVER_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not CONFIG_SERVER_PATH.exists():
        shutil.copy(SOURCE_CONFIG_SERVER, CONFIG_SERVER_PATH)
        log.info(f"Copied {SOURCE_CONFIG_SERVER} to {CONFIG_SERVER_PATH}")
    else:
        log.info(f"{CONFIG_SERVER_PATH} already exists.")


def check_config_permission(config_dict: dict):
    """
    Check if the specified directories in config.yaml are writable. If not, switches to a fallback directory.
    Handles both server and client configurations.

    Args:
        config_dict (dict): The configuration dictionary loaded from YAML.
    """
    # Define paths to check based on config type
    paths_to_check = {
        ("api", "cert_path"): config_dict.get("api", {}).get("cert_path"),
        ("database", "sqlite", "location"): config_dict.get("database", {})
        .get("sqlite", {})
        .get("location"),
        ("starkiller", "directory"): config_dict.get("starkiller", {}).get("directory"),
        ("logging", "directory"): config_dict.get("logging", {}).get("directory"),
        ("debug", "last_task", "file"): config_dict.get("debug", {})
        .get("last_task", {})
        .get("file"),
        ("plugin_marketplace", "directory"): config_dict.get(
            "plugin_marketplace", {}
        ).get("directory"),
        ("directories", "downloads"): config_dict.get("directories", {}).get(
            "downloads"
        ),
    }
    config_path = CONFIG_SERVER_PATH  # Use the server config path

    # Check permissions and update paths as needed
    for keys, dir_path in paths_to_check.items():
        if dir_path is None:
            continue

        current_dir = dir_path
        while current_dir and not os.path.exists(current_dir):
            current_dir = os.path.dirname(current_dir)

        if not os.access(current_dir, os.W_OK):
            log.info(
                "No write permission for %s. Switching to fallback directory.",
                current_dir,
            )
            user_home = Path.home()
            fallback_dir = os.path.join(
                user_home, ".empire", str(current_dir).removeprefix("empire/")
            )

            # Update the directory in config_dict
            target = config_dict  # target is a reference to config_dict
            for key in keys[:-1]:
                target = target[key]
            target[keys[-1]] = fallback_dir

            log.info(
                "Updated %s to fallback directory: %s", "->".join(keys), fallback_dir
            )

    # Write the updated configuration back to the correct YAML file
    with open(config_path, "w") as config_file:
        yaml.safe_dump(paths2str(config_dict), config_file)

    return config_dict


def paths2str(data):
    if isinstance(data, dict):
        return {key: paths2str(value) for key, value in data.items()}
    if isinstance(data, list):
        return [paths2str(item) for item in data]
    if isinstance(data, Path):
        return str(data)
    return data
