import subprocess
import tempfile
from pathlib import Path

from empire.server.common.helpers import random_string


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

    try:
        subprocess.run(["git", "clone", git_url, directory], check=True)
    except subprocess.CalledProcessError:
        raise GitOperationException(
            f"Failed to clone git repository: {git_url}"
        ) from None

    if ref:
        try:
            subprocess.run(["git", "checkout", ref], cwd=directory, check=True)
        except subprocess.CalledProcessError:
            raise GitOperationException(f"Failed to check out ref {ref}") from None

    return directory
