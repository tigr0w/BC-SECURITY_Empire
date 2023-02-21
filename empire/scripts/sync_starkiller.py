import logging
import os
import subprocess

log = logging.getLogger(__name__)


def sync_starkiller(empire_config):
    """
    Syncs the starkiller submodule with what is in the config.
    Using dict acccess because this script should be able to run with minimal packages, not just within empire.
    """
    starkiller_config = empire_config["starkiller"]
    starkiller_submodule_dir = "empire/server/api/v2/starkiller"
    starkiller_temp_dir = "empire/server/api/v2/starkiller-temp"

    subprocess.run(["git", "submodule", "update", "--init", "--recursive"], check=True)

    if not starkiller_config["use_temp_dir"]:
        log.info("Syncing starkiller submodule to match config.yaml")
        subprocess.run(
            [
                "git",
                "submodule",
                "set-url",
                "--",
                starkiller_submodule_dir,
                starkiller_config["repo"],
            ],
            check=True,
        )
        subprocess.run(
            ["git", "submodule", "sync", "--", starkiller_submodule_dir], check=True
        )

        _fetch_checkout_pull(starkiller_config["ref"], starkiller_submodule_dir)

    else:
        if not os.path.exists(starkiller_temp_dir):
            log.info("Cloning starkiller to temp dir")
            subprocess.run(
                ["git", "clone", starkiller_config["repo"], starkiller_temp_dir],
                check=True,
            )

        else:
            log.info("Updating starkiller temp dir")
            subprocess.run(
                ["git", "remote", "set-url", "origin", starkiller_config["repo"]],
                cwd=starkiller_temp_dir,
                check=True,
            )

        _fetch_checkout_pull(starkiller_config["ref"], starkiller_temp_dir)


def _fetch_checkout_pull(ref, cwd):
    subprocess.run(["git", "fetch"], cwd=cwd, check=True)
    subprocess.run(
        ["git", "checkout", ref],
        cwd=cwd,
        check=True,
    )
    subprocess.run(["git", "pull", "origin", ref], cwd=cwd)
