import contextlib
import subprocess
import tempfile
from pathlib import Path

from empire.server.common.helpers import random_string
from empire.server.utils.file_util import run_as_user


class GitOperationException(Exception):
    pass


def clone_git_repo(
    git_url: str, ref: str | None = None, directory: Path | None = None
) -> Path:
    """
    Clones a git repository to a directory and checks out a specific ref if provided.

    :param git_url: The git URL to clone
    :param directory: The directory to clone the git repository to. If None, a temporary directory is used.
    :param ref: The ref to check out
    :return: The directory the git repository was cloned to
    """
    if directory is None:
        directory = (
            Path(tempfile.gettempdir())
            / random_string(5)
            / git_url.removesuffix(".git").split("/")[-1]
        )
    directory.mkdir(parents=True, exist_ok=True)

    try:
        run_as_user(["git", "clone", git_url, directory])
    except subprocess.CalledProcessError:
        raise GitOperationException(
            f"Failed to clone git repository: {git_url}"
        ) from None

    if ref:
        try:
            run_as_user(["git", "checkout", ref], cwd=directory)
        except subprocess.CalledProcessError:
            raise GitOperationException(f"Failed to check out ref {ref}") from None

    return directory


def update_git_repo(directory: Path) -> bool:
    """
    Does a git pull on the provided directory. If it can't be pulled, it's ignored.
    """
    with contextlib.suppress(subprocess.CalledProcessError):
        run_as_user(["git", "pull"], cwd=directory)

    return True
