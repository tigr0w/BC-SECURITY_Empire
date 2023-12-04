import logging
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


def sync_starkiller(empire_config):
    """
    Syncs the starkiller directory with what is in the config.
    Using dict access because this script should be able to run with minimal packages,
    not just within empire server.
    """
    starkiller_config = empire_config["starkiller"]
    starkiller_dir = starkiller_config["directory"]

    if not Path(starkiller_dir).exists():
        log.info("Starkiller: directory not found. Cloning Starkiller")
        _clone_starkiller(starkiller_config, starkiller_dir)

    if starkiller_config.get("auto_update"):
        log.info("Starkiller: Autoupdate on. Pulling latest ref.")
        _fetch_checkout_pull(
            starkiller_config["repo"], starkiller_config["ref"], starkiller_dir
        )


def _clone_starkiller(starkiller_config: dict, starkiller_dir: str):
    subprocess.run(
        ["git", "clone", starkiller_config["repo"], starkiller_dir],
        check=True,
    )


def _fetch_checkout_pull(remote_repo, ref, cwd):
    subprocess.run(
        ["git", "remote", "set-url", "origin", remote_repo],
        cwd=cwd,
        check=True,
    )

    subprocess.run(["git", "fetch"], cwd=cwd, check=True)
    subprocess.run(
        ["git", "checkout", ref],
        cwd=cwd,
        check=True,
    )
    subprocess.run(["git", "pull", "origin", ref], cwd=cwd)
