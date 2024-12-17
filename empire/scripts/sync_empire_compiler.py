import logging
from pathlib import Path

from empire.server.utils.file_util import run_as_user

log = logging.getLogger(__name__)


def get_architecture():
    """
    Detect the system architecture and return the corresponding value.
    """
    import platform

    arch = platform.machine()
    if arch == "x86_64":
        return "linux-x64"
    if arch in ["aarch64", "arm64"]:
        return "linux-arm64"
    return "unsupported"


def _clone_empire_compiler(repo_url, ref, repo_path):
    """
    Clones the Empire Compiler repository at the specified ref as the specified user.
    """
    log.info(f"Cloning Empire Compiler repository {repo_url} at ref {ref}.")
    run_as_user(
        [
            "git",
            "clone",
            "--branch",
            ref,
            "--recursive",
            "--depth",
            "1",
            repo_url,
            str(repo_path),
        ]
    )


def fetch_checkout_pull(remote_repo, ref, cwd):
    """
    Fetches the latest updates for the repository and checks out the specified ref.
    Returns the currently checked out version after pulling.
    """
    run_as_user(["git", "remote", "set-url", "origin", remote_repo], cwd=cwd)
    run_as_user(["git", "fetch"], cwd=cwd)
    run_as_user(["git", "checkout", ref], cwd=cwd)
    run_as_user(["git", "pull", "origin", ref], cwd=cwd)

    return run_as_user(
        ["git", "describe", "--tags"],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def download_file(url, target_path):
    """
    Download a file from a given URL and save it to the target path.
    """
    import requests

    log.info(f"Downloading file from {url} to {target_path}.")
    response = requests.get(url, stream=True)
    if response.status_code == 200:  # noqa: PLR2004
        with open(target_path, "wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)
        log.info(f"Successfully downloaded file to {target_path}.")
    else:
        log.error(
            f"Failed to download file from {url}. Status code: {response.status_code}"
        )
        response.raise_for_status()


def load_empire_compiler(empire_config):
    """
    Syncs the Empire Compiler directory with what is in the config.
    Determines the latest version and ensures the repository is up to date.
    """
    compiler_config = empire_config.empire_compiler
    repo_path = Path(compiler_config.directory)
    repo_url = compiler_config.repo
    base_version = compiler_config.version
    architecture = get_architecture()

    if architecture == "unsupported":
        log.error("Unsupported system architecture. Exiting.")
        return

    if repo_url.startswith("https://github.com/"):
        parts = repo_url[len("https://github.com/") :].rstrip(".git").split("/")
        if len(parts) != 2:  # noqa: PLR2004
            log.error(f"Invalid HTTPS repository URL: {repo_url}")
            return
        org, repo_name = parts
    elif repo_url.startswith("git@github.com:"):
        parts = repo_url[len("git@github.com:") :].rstrip(".git").split("/")
        if len(parts) != 2:  # noqa: PLR2004
            log.error(f"Invalid SSH repository URL: {repo_url}")
            return
        org, repo_name = parts
    else:
        log.error(f"Invalid repository URL format: {repo_url}")
        return

    latest_version = get_latest_patch_version(empire_config, base_version)
    binary_url = f"https://github.com/{org}/{repo_name}/releases/download/{latest_version}/EmpireCompiler-{architecture}"
    binary_path = repo_path / "EmpireCompiler" / "EmpireCompiler"
    binary_needs_replacement = False

    if not repo_path.exists():
        log.info(
            f"Empire Compiler: Directory not found. Cloning repository at version {latest_version}."
        )
        _clone_empire_compiler(repo_url, latest_version, repo_path)
        binary_needs_replacement = True

    elif compiler_config.auto_update:
        log.info("Empire Compiler: Autoupdate on. Pulling latest changes.")
        current_version = fetch_checkout_pull(repo_url, latest_version, repo_path)
        binary_needs_replacement = current_version != latest_version

    if (
        binary_needs_replacement
        or not binary_path.is_file()
        or binary_path.stat().st_size == 0
    ):
        log.info(f"Downloading Empire Compiler binary for version {latest_version}.")
        download_file(binary_url, binary_path)
        binary_path.chmod(0o755)
        log.info(
            f"Empire Compiler binary for {latest_version} successfully downloaded."
        )
    else:
        log.info("Empire Compiler binary already exists and is up to date.")


def get_latest_patch_version(empire_config, base_version):
    """
    Fetch the latest patch version for a given base version (major.minor) from the GitHub API.
    """
    import requests

    compiler_config = empire_config.empire_compiler
    repo_url = compiler_config.repo

    if repo_url.startswith("https://github.com/"):
        parts = repo_url[len("https://github.com/") :].rstrip(".git").split("/")
    elif repo_url.startswith("git@github.com:"):
        parts = repo_url[len("git@github.com:") :].rstrip(".git").split("/")
    else:
        log.error(f"Invalid repository URL format for GitHub API: {repo_url}")
        return f"{base_version}.0"

    if len(parts) != 2:  # noqa: PLR2004
        log.error(f"Could not parse repository URL for GitHub API: {repo_url}")
        return f"{base_version}.0"

    org, repo_name = parts
    api_url = f"https://api.github.com/repos/{org}/{repo_name}/releases"

    try:
        response = requests.get(api_url)
        response.raise_for_status()

        releases = response.json()
        matching_versions = [
            release["tag_name"]
            for release in releases
            if release["tag_name"].startswith(base_version)
        ]

        if matching_versions:
            return sorted(
                matching_versions,
                key=lambda v: list(map(int, v.lstrip("v").split("."))),
            )[-1]
        return f"{base_version}.0"
    except requests.RequestException as e:
        log.error(f"Error fetching the latest patch version: {e}")
        return f"{base_version}.0"
