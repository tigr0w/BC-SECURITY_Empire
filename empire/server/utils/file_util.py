import logging
import os
import pwd
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


def ensure_user_ownership(path: Path, user: str | None = None) -> None:
    """Recursively chown `path` to `user` (default $SUDO_USER) when running as root.

    No-op unless we're root and a non-root target user is resolvable — this
    exists because ps-empire runs Python via `sudo -E`, so files created
    directly by the Python process (e.g. `shutil.copytree`) end up root-owned,
    which then trips git's "dubious ownership" safeguard when the update path
    drops back to the invoking user via `run_as_user`.
    """
    if os.geteuid() != 0:
        return
    if user is None:
        user = os.environ.get("SUDO_USER")
    if not user or user == "root":
        return
    try:
        pw = pwd.getpwnam(user)
    except KeyError:
        log.warning(f"ensure_user_ownership: user '{user}' not found; skipping chown")
        return

    uid, gid = pw.pw_uid, pw.pw_gid
    try:
        st = path.stat()
    except FileNotFoundError:
        return
    if st.st_uid == uid and st.st_gid == gid:
        return

    log.info(f"Fixing ownership of {path} -> {user}:{user}")
    try:
        os.chown(path, uid, gid)
    except (PermissionError, OSError):
        # Surfacing this matters: if chown fails, the downstream git commands
        # will hit "dubious ownership" again, and callers should know why.
        log.exception(
            f"ensure_user_ownership: chown on {path} failed; "
            "downstream git operations may fail with 'dubious ownership'. "
            f"Fix ownership manually (e.g. `sudo chown -R $USER {path}`)."
        )
        raise
    for root, dirs, files in os.walk(path):
        root_path = Path(root)
        for name in dirs + files:
            entry = root_path / name
            try:
                os.chown(entry, uid, gid, follow_symlinks=False)
            except FileNotFoundError:
                continue
            except (PermissionError, OSError) as e:
                # Don't abort the rest of the walk over a single un-chownable
                # entry — the user can re-run after fixing it manually.
                log.warning(
                    f"ensure_user_ownership: chown {entry} failed ({e}); continuing"
                )


def run_as_user(  # noqa: PLR0913
    command, user=None, cwd=None, capture_output=False, check=True, text=True
):
    """
    Runs a command as a specified user or the user who invoked sudo.
    If no user is specified and the script is not run with sudo, it runs as the current user.

    Args:
        command (list): The command to run, specified as a list of strings.
        user (str, optional): The username to run the command as. Defaults to None.
        cwd (str, optional): The working directory for the command. Defaults to None.
        capture_output (bool, optional): Whether to capture and return the command's output. Defaults to False.

    Returns:
        str or None: The output of the command if capture_output is True, otherwise None.
    """
    try:
        if user is None:
            user = os.getenv("SUDO_USER")

        # Avoid sudo if target user is root or empty (typical in containers)
        if user in (None, "", "root"):
            command_with_user = command
        else:
            # Preserve env (-E) so SSH_AUTH_SOCK / GIT_SSH_COMMAND are available
            command_with_user = ["sudo", "-E", "-u", user, *command]

        result = subprocess.run(
            command_with_user,
            check=check,
            cwd=cwd,
            text=text,
            capture_output=capture_output,
        )
    except subprocess.CalledProcessError as e:
        log.exception("Failed to execute command")
        log.info(
            "Try running the command manually: %s", " ".join([str(c) for c in command])
        )
        if e.stdout:
            log.warning("Command output: %s", e.stdout)
        if e.stderr:
            log.warning("Command error output: %s", e.stderr)
        raise
    else:
        log.debug("Command executed successfully: %s", " ".join(map(str, command)))

        if capture_output:
            return result.stdout.strip()
        return None
