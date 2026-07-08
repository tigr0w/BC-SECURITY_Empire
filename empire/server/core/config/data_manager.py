import logging
import os
import platform
import pwd
import shutil
import subprocess
import tarfile
from pathlib import Path

import requests

from empire.server.core.config import config_manager
from empire.server.core.config.config_manager import (
    EmpireCompilerConfig,
    PluginRegistryConfig,
    StarkillerConfig,
)
from empire.server.utils.file_util import run_as_user
from empire.server.utils.git_util import GitOperationException, clone_git_repo

log = logging.getLogger(__name__)


def sync_starkiller(starkiller_config: StarkillerConfig):
    starkiller_dir = config_manager.DATA_DIR / "starkiller" / starkiller_config.ref

    if not Path(starkiller_dir).exists():
        log.info("Starkiller: directory not found. Cloning Starkiller")
        clone_git_repo(starkiller_config.repo, starkiller_config.ref, starkiller_dir)

    return starkiller_dir


def _resolve_compiler_platform():
    """Return (os, arch) strings used in compiler asset names, or (None, None)."""
    os_ = platform.system()
    arch = platform.machine()

    if os_ == "Darwin":
        os_ = "osx"
    elif os_ == "Linux":
        os_ = "linux"
    else:
        log.error(f"Empire Compiler: unsupported OS '{os_}'")
        return None, None

    if arch == "x86_64":
        arch = "x64"
    elif arch in ["aarch64", "arm64"]:
        arch = "arm64"
    else:
        log.error(f"Empire Compiler: unsupported architecture '{arch}'")
        return None, None

    return os_, arch


def _github_api_headers() -> dict[str, str]:
    """Headers for the GitHub REST API.

    Adds bearer auth when ``GITHUB_TOKEN``/``GH_TOKEN`` is present so requests
    aren't subject to GitHub's 60 req/hr unauthenticated limit. That limit is
    keyed on the egress IP, which CI runners share, so unauthenticated calls
    routinely 403 during test runs.
    """
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _resolve_compiler_download_url(
    compiler_config: EmpireCompilerConfig, platform_str: str
) -> str | None:
    """Resolve the download URL for the compiler archive.

    Queries the GitHub Releases API using ``repo`` and ``ref``.
    """
    if not compiler_config.repo or not compiler_config.ref:
        log.error("Empire Compiler: 'repo' and 'ref' must be configured")
        return None

    api_url = f"https://api.github.com/repos/{compiler_config.repo}/releases/tags/{compiler_config.ref}"
    log.info(f"Empire Compiler: querying GitHub release {api_url}")
    resp = requests.get(api_url, timeout=30, headers=_github_api_headers())
    if not resp.ok:
        log.error(
            f"Empire Compiler: failed to fetch release info ({resp.status_code}): {resp.text}"
        )
        return None

    assets = resp.json().get("assets", [])
    for asset in assets:
        name = asset.get("name", "")
        if platform_str in name and name.endswith(".tgz"):
            return asset["browser_download_url"]

    log.error(
        f"Empire Compiler: no matching asset for platform '{platform_str}' in release {compiler_config.ref}"
    )
    return None


def _configure_compiler(
    compiler_config: EmpireCompilerConfig, extracted_folder: Path
) -> Path:
    """Write the ConfuserEx project file if it doesn't already exist."""
    confuser_proj_dir = extracted_folder / "EmpireCompiler"
    confuser_base_dir = confuser_proj_dir / "Data" / "Temp"
    confuser_output_dir = confuser_base_dir / "confused_out"
    confuser_project_file = confuser_base_dir / "empire.crproj"

    if not confuser_project_file.exists():
        confuser_template = Path(compiler_config.confuser_proj).read_text()
        confuser_project_file.parent.mkdir(parents=True, exist_ok=True)
        confuser_project_file.write_text(
            confuser_template.format(
                confuser_base_dir=confuser_base_dir,
                confuser_output_dir=confuser_output_dir,
                confuser_module_path="confused.exe",
                confuser_proj_dir=confuser_proj_dir,
            ),
            encoding="utf-8",
        )

    return extracted_folder


def sync_empire_compiler(compiler_config: EmpireCompilerConfig):
    # Allow a local directory override so developers can test without
    # publishing a GitHub release (mirrors how Starkiller handles this).
    if compiler_config.directory:
        local_dir = Path(compiler_config.directory)
        if local_dir.exists():
            log.info(f"Empire Compiler: using local directory {local_dir}")
            return _configure_compiler(compiler_config, local_dir)
        log.warning(
            f"Empire Compiler: configured directory '{compiler_config.directory}' does not exist, falling back to download"
        )

    os_, arch = _resolve_compiler_platform()
    if os_ is None:
        return None

    platform_str = f"{os_}-{arch}"
    compiler_dir = config_manager.DATA_DIR / "empire-compiler"

    # Check for an existing directory matching this platform *and* version
    # before hitting the GitHub API, so cached compilers don't require
    # network access.
    expected_suffix = f"{platform_str}-{compiler_config.ref}"
    if compiler_dir.exists():
        for d in compiler_dir.iterdir():
            if d.is_dir() and expected_suffix in d.name:
                log.info(f"Empire Compiler: using cached {d.name}")
                return _configure_compiler(compiler_config, d)

    url = _resolve_compiler_download_url(compiler_config, platform_str)
    if url is None:
        return None

    name = url.split("/")[-1].removesuffix(".tgz")

    if not Path(compiler_dir / name).exists():
        log.info("Empire Compiler: directory not found. Downloading Empire Compiler")
        log.info(f"Empire Compiler: fetching and unarchiving {url}")
        compiler_dir.mkdir(parents=True, exist_ok=True)
        with (
            requests.get(url, stream=True, timeout=(30, 300)) as resp,
            tarfile.open(fileobj=resp.raw, mode="r|gz") as tar,
        ):
            # filter="data" guards against path traversal in the downloaded archive.
            tar.extractall(compiler_dir, filter="data")

    extracted_folder = compiler_dir / name
    return _configure_compiler(compiler_config, extracted_folder)


def _banner(msg: str) -> None:
    """User-facing status line for the `update` subcommand.

    The `update` entry point does not initialise the server logger, so `log.*`
    output is suppressed. Print directly so operators can see what's being
    checked.
    """
    print(f"\x1b[1;34m[*] {msg}\x1b[0m", flush=True)


def _warn(msg: str) -> None:
    print(f"\x1b[1;33m[!] {msg}\x1b[0m", flush=True)


def _error(msg: str) -> None:
    print(f"\x1b[1;31m[x] {msg}\x1b[0m", flush=True)


def _confirm(prompt: str, *, assume_yes: bool) -> bool:
    if assume_yes:
        log.info(f"{prompt} [auto-yes]")
        return True
    try:
        answer = input(f"{prompt} [y/N]: ")
    except EOFError:
        # Non-interactive without -y is ambiguous: the caller intends to
        # update, but we'd silently skip migrations and the aggregator would
        # report success. Exit non-zero so CI / scripted callers notice
        # rather than relying on operators to spot a missed prompt in logs.
        _error(
            "No interactive TTY and -y not provided; refusing to silently "
            "skip migration. Re-run with -y to auto-confirm."
        )
        raise SystemExit(2) from None
    return answer.strip().lower() in ("y", "yes")


def _git_fast_forward(target: Path, ref: str, label: str) -> bool:
    """Fetch + checkout + fast-forward pull at `target`. Returns success.

    Used by `update_starkiller` / `update_plugin_registry` Case A. The loop
    raises out of the shared try/except as soon as a step fails, so the
    user-facing error names the failing command (via `e.cmd`) instead of a
    generic "git update failed".
    """
    _banner(f"{label}: checking for updates at {target} (ref: {ref})")
    # `config.yaml` documents Starkiller's `ref` as branch/tag/commit. Tags
    # and SHAs land on detached HEAD after checkout, where `git pull --ff-only`
    # errors with "You are not currently on a branch". Probe with
    # `branch --show-current` (empty stdout on detached HEAD) and skip the
    # pull in that case — there's nothing to fast-forward when HEAD is
    # already pinned to a fixed commit.
    for step, cmd in (
        ("fetch", ["git", "fetch", "--tags"]),
        ("checkout", ["git", "checkout", ref]),
    ):
        try:
            run_as_user(cmd, cwd=target)
        except subprocess.CalledProcessError as e:
            _error(
                f"{label}: git {step} failed at {target} "
                f"(cmd: {' '.join(str(c) for c in e.cmd)}, rc: {e.returncode}). "
                "Resolve manually or remove the directory to force a re-clone."
            )
            return False

    try:
        branch = run_as_user(
            ["git", "branch", "--show-current"], cwd=target, capture_output=True
        ).strip()
    except subprocess.CalledProcessError:
        branch = ""
    if not branch:
        _banner(f"{label}: pinned to '{ref}' (detached HEAD); skipping pull")
        return True

    try:
        run_as_user(["git", "pull", "--ff-only"], cwd=target)
    except subprocess.CalledProcessError as e:
        _error(
            f"{label}: git pull failed at {target} "
            f"(cmd: {' '.join(str(c) for c in e.cmd)}, rc: {e.returncode}). "
            "Resolve manually or remove the directory to force a re-clone."
        )
        return False
    return True


def overwrite_base_config(repo_root: Path) -> bool:
    """Copy the shipped `config.yaml` over the user's active base config.

    Customizations belong in `config.user.yaml` under the config dir, which the
    layered loader (`config_manager.EmpireConfig.settings_customise_sources`)
    merges on top of the base — so treating the base as team-owned defaults
    lets us ship new refs (compiler, starkiller, registries) without trying
    to reconcile them against the user's edits.
    """
    src = repo_root / "empire" / "server" / "config.yaml"
    dst = config_manager.CONFIG_PATH
    if not src.exists():
        _error(f"Config: shipped template missing at {src}; skipping overwrite")
        return False
    if src.resolve() == dst.resolve():
        _banner(f"Config: {dst} already points at the shipped template; skipping copy")
        return True
    try:
        shutil.copy(src, dst)
    except OSError as e:
        # PermissionError (e.g. dst is root-owned from a prior sudo install) and
        # any other OSError — surface it and let the rest of run_update proceed.
        _error(
            f"Config: could not overwrite {dst} from {src} ({e}). "
            f"Fix permissions (e.g. `sudo chown $USER {dst}`) and re-run "
            "'./ps-empire update'."
        )
        return False
    _banner(f"Config: overwrote {dst} from {src}")
    return True


def _detect_release_channel(repo_root: Path) -> str | None:
    """Return the `checkout-latest-tag.sh` channel arg matching the origin remote.

    `Empire-Sponsors` -> `sponsors`, `Empire-Kali` -> `kali`, otherwise None
    (mainline Empire — script picks the latest non-prerelease semver tag).
    Returning None on a *failed* read (vs. an unknown URL) would silently
    downgrade sponsors/kali installs to mainline tags, so warn loudly in that
    case to leave a greppable breadcrumb.
    """
    try:
        url = run_as_user(
            ["git", "remote", "get-url", "origin"],
            cwd=repo_root,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        _warn(
            f"Empire: could not read 'origin' remote at {repo_root} "
            f"(cmd: {' '.join(str(c) for c in e.cmd)}, rc: {e.returncode}); "
            "treating as mainline. If this is a sponsors/kali install, restore "
            "the 'origin' remote and re-run './ps-empire update'."
        )
        return None
    if not url:
        _warn(
            f"Empire: 'origin' remote at {repo_root} returned an empty URL; "
            "treating as mainline. If this is a sponsors/kali install, restore "
            "the remote and re-run './ps-empire update'."
        )
        return None
    if "Empire-Sponsors" in url:
        return "sponsors"
    if "Empire-Kali" in url:
        return "kali"
    return None


def update_empire_source(repo_root: Path) -> bool:
    """Move the Empire checkout to the latest release tag.

    Mirrors the documented install path (`setup/checkout-latest-tag.sh`), so
    users who installed at a tag stay on a stable release. For dev branches
    (`sponsors-main`, `7.0-dev`, etc.) we skip and let the user manage source
    updates themselves — `git pull` from a detached HEAD fails outright, and
    silently fast-forwarding a tracking branch isn't what most users want.
    """
    if not (repo_root / ".git").exists():
        _banner(f"Empire: {repo_root} is not a git checkout, skipping")
        return True

    _banner(f"Empire: checking for updates at {repo_root}")
    # `git branch --show-current` returns the branch name on a branch and
    # empty stdout on detached HEAD, exiting 0 either way.
    try:
        run_as_user(["git", "fetch", "--tags"], cwd=repo_root)
        branch = run_as_user(
            ["git", "branch", "--show-current"],
            cwd=repo_root,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        _error(
            f"Empire: `{' '.join(str(c) for c in e.cmd)}` failed at {repo_root} "
            f"(rc: {e.returncode}). Resolve manually and re-run './ps-empire update'."
        )
        return False

    if branch:
        _warn(
            f"Empire: HEAD is on branch '{branch}'; this is a development "
            "branch — manage source updates manually with git. Skipping the "
            "source step (config and downstream refreshes will still run)."
        )
        return True

    script = repo_root / "setup" / "checkout-latest-tag.sh"
    if not script.exists():
        _error(f"Empire: {script} not found; cannot move to latest release tag")
        return False

    cmd = ["bash", str(script)]
    channel = _detect_release_channel(repo_root)
    if channel:
        cmd.append(channel)
    try:
        run_as_user(cmd, cwd=repo_root)
    except subprocess.CalledProcessError as e:
        _error(
            f"Empire: checkout-latest-tag.sh failed (rc: {e.returncode}). "
            "Resolve manually and re-run './ps-empire update'."
        )
        return False
    return True


def update_starkiller(
    starkiller_config: StarkillerConfig, *, assume_yes: bool = False
) -> bool:
    starkiller_root = config_manager.DATA_DIR / "starkiller"
    target = starkiller_root / starkiller_config.ref

    if target.exists() and (target / ".git").exists():
        return _git_fast_forward(target, starkiller_config.ref, "Starkiller")

    cached = (
        [p.name for p in starkiller_root.iterdir() if p.is_dir()]
        if starkiller_root.exists()
        else []
    )
    if cached:
        _banner(
            f"Starkiller: cached refs {cached}; config ref is '{starkiller_config.ref}'"
        )
        if not _confirm(
            f"Download Starkiller '{starkiller_config.ref}' and migrate?",
            assume_yes=assume_yes,
        ):
            _banner("Starkiller: migration skipped")
            return True

    _banner(f"Starkiller: cloning '{starkiller_config.ref}' (first run)")
    try:
        sync_starkiller(starkiller_config)
    except GitOperationException as e:
        _error(f"Starkiller: clone failed ({e}).")
        return False
    return True


def update_empire_compiler(
    compiler_config: EmpireCompilerConfig, *, assume_yes: bool = False
) -> bool:
    if compiler_config.directory:
        _banner(
            f"Empire Compiler: using local directory override {compiler_config.directory}; nothing to update"
        )
        return True

    os_, arch = _resolve_compiler_platform()
    if os_ is None:
        return False

    platform_str = f"{os_}-{arch}"
    compiler_dir = config_manager.DATA_DIR / "empire-compiler"
    expected_suffix = f"{platform_str}-{compiler_config.ref}"

    cached_names = []
    if compiler_dir.exists():
        for d in compiler_dir.iterdir():
            if d.is_dir():
                cached_names.append(d.name)
                if expected_suffix in d.name:
                    _banner(
                        f"Empire Compiler: already on '{compiler_config.ref}' ({d.name}); up to date"
                    )
                    return True

    if cached_names:
        _banner(
            f"Empire Compiler: cached {cached_names}; config ref is '{compiler_config.ref}'"
        )
        if not _confirm(
            f"Download Empire Compiler '{compiler_config.ref}' and migrate?",
            assume_yes=assume_yes,
        ):
            _banner("Empire Compiler: migration skipped")
            return True

    _banner(f"Empire Compiler: downloading '{compiler_config.ref}'")
    # sync_empire_compiler returns None (without raising) for unsupported
    # OS/arch, missing repo/ref config, GitHub API non-OK (rate limit,
    # 404, DNS), and no asset matching the resolved platform — and raises
    # on network/disk/extract failures. Without this check the aggregator
    # prints "[*] Update complete." and the user hits the actual error
    # several layers downstream. Funnel both cases through a single error
    # path to keep the return count under PLR0911's threshold.
    error_detail: str | None = None
    try:
        result = sync_empire_compiler(compiler_config)
    except (requests.RequestException, tarfile.TarError, OSError) as e:
        error_detail = f"download/extract failed ({e})."
    else:
        if result is None:
            error_detail = (
                "sync returned no path (unsupported platform, missing asset, "
                "or API failure). Check the server log for the underlying cause."
            )
    if error_detail:
        _error(f"Empire Compiler: {error_detail}")
        return False
    return True


def update_plugin_registry(
    registry_config: PluginRegistryConfig, *, assume_yes: bool = False
) -> bool:
    if not registry_config.git_url:
        return True

    ref = registry_config.ref or "main"
    base_dir = config_manager.DATA_DIR / "plugin-registries" / registry_config.name
    target = base_dir / ref

    if target.exists() and (target / ".git").exists():
        return _git_fast_forward(
            target, ref, f"Plugin Registry '{registry_config.name}'"
        )

    cached = (
        [p.name for p in base_dir.iterdir() if p.is_dir()] if base_dir.exists() else []
    )
    if cached:
        _banner(
            f"Plugin Registry '{registry_config.name}': cached refs {cached}; config ref is '{ref}'"
        )
        if not _confirm(
            f"Download plugin registry '{registry_config.name}' at '{ref}' and migrate?",
            assume_yes=assume_yes,
        ):
            _banner(f"Plugin Registry '{registry_config.name}': migration skipped")
            return True

    _banner(f"Plugin Registry '{registry_config.name}': cloning '{ref}' (first run)")
    try:
        sync_plugin_registry(registry_config)
    except GitOperationException as e:
        _error(f"Plugin Registry '{registry_config.name}': clone failed ({e}).")
        return False
    return True


def _ownership_check_paths() -> list[Path]:
    """Paths the pre-flight should stat for foreign ownership.

    Includes the obvious roots plus the immediate children of `DATA_DIR`
    that contain `.git/` clones (Starkiller, plugin registries) — those are
    where prior `sudo` installs left root-owned trees that trip git's
    "dubious ownership" check, even when `DATA_DIR` itself is user-owned.
    """
    paths = [
        config_manager.CONFIG_DIR,
        config_manager.CONFIG_PATH,
        config_manager.DATA_DIR,
    ]
    for subdir_name in ("starkiller", "plugin-registries", "empire-compiler"):
        subdir = config_manager.DATA_DIR / subdir_name
        if not subdir.exists():
            continue
        paths.append(subdir)
        try:
            paths.extend(p for p in subdir.iterdir() if p.is_dir())
        except OSError:
            # Can't enumerate children — the parent itself will surface the
            # ownership problem if there is one.
            continue
    return paths


def _foreign_owned_paths() -> tuple[list[Path], list[Path]]:
    """Return (foreign-owned, unstat-able) lists.

    Foreign-owned paths exist and are owned by another uid (typically root,
    left behind by a prior `sudo` invocation of `install`/`setup`/`update`
    before this PR moved `setup`/`update` off sudo). Unstat-able paths
    couldn't be checked at all (broken filesystem, EACCES on stat); they're
    returned separately so the caller can warn rather than silently treating
    them as clean. A single `stat` (not `exists` + `stat`) is used so that
    `PermissionError` lands in `unstat` instead of being swallowed by
    `Path.exists`'s built-in OSError → False fallback.
    """
    current_uid = os.getuid()
    foreign: list[Path] = []
    unstat: list[Path] = []
    for p in _ownership_check_paths():
        try:
            st = p.stat()
        except FileNotFoundError:
            continue
        except OSError:
            unstat.append(p)
            continue
        if st.st_uid != current_uid:
            foreign.append(p)
    return foreign, unstat


def _current_username() -> str:
    """Resolve the current user's name for the chown remediation hint.

    Prefers `$USER` (set in normal login shells); falls back to the passwd
    database; finally falls back to the numeric uid for slim containers /
    distroless / deleted-account cases where neither is available.
    """
    user = os.environ.get("USER")
    if user:
        return user
    try:
        return pwd.getpwuid(os.getuid()).pw_name
    except KeyError:
        return str(os.getuid())


def check_no_foreign_ownership() -> bool:
    """Pre-flight for `setup` / `update`: bail with a single actionable banner
    if any of the user's Empire dirs are owned by another user. Without this,
    the calling subcommand fails partway through — `shutil.copy` hits `EPERM`,
    and `git fetch` inside root-owned clones hits "dubious ownership" — and
    the user is left to piece together the remediation from per-step errors.
    """
    foreign, unstat = _foreign_owned_paths()
    for p in unstat:
        _warn(f"Could not stat {p}; ownership unknown — continuing.")
    if not foreign:
        return True

    _error(
        "Detected files owned by another user (likely root from a prior "
        "`sudo` invocation of install/setup/update). `./ps-empire setup` and "
        "`update` no longer run under sudo, so they cannot write to "
        "root-owned paths."
    )
    for p in foreign:
        print(f"    {p}", flush=True)
    _error(
        f"Fix once with:\n"
        f"    sudo chown -R {_current_username()} {config_manager.CONFIG_DIR} "
        f"{config_manager.DATA_DIR}\n"
        "Then re-run the command that triggered this."
    )
    return False


def update_database(*, assume_yes: bool) -> bool:
    """Back up the database (if possible) then apply any pending Alembic
    migrations.

    Run as part of `./ps-empire update` so users don't have to start the
    server, watch it crash on a schema mismatch, and chase the recovery
    advice manually. Idempotent: a no-op when the schema is already at
    head.

    Returns True on success (including the no-op case), False if the user
    declines to migrate or the migration itself fails. Backup failures do
    not block the migration — the operator is warned and the upgrade
    proceeds, since the alternative (refusing to migrate) would leave the
    server unbootable on environments where mysqldump isn't installed.
    """
    _banner("Database: checking for pending migrations")
    # Lazy import: empire.server.core.db.base has heavy module-level side
    # effects (creates the SQLAlchemy engine, runs Base.metadata.create_all).
    # Defer until the update flow actually needs the DB so a `--help` or a
    # pre-flight failure doesn't pay that cost.
    try:
        from empire.server.core.db import base as db_base
    except Exception:
        _error(
            "Database: failed to import the DB module; cannot check "
            "migrations. See traceback above."
        )
        log.exception("Database: import failed")
        return False

    try:
        current, head = db_base.pending_migrations()
    except Exception:
        _error(
            "Database: failed to read Alembic revision state. Check that "
            "the database is reachable and the alembic package is installed."
        )
        log.exception("Database: revision check failed")
        return False

    if current == head:
        _banner(f"Database: schema up to date at revision {current}")
        return True

    label = f"untracked → '{head}'" if current is None else f"'{current}' → '{head}'"
    _banner(f"Database: pending migrations ({label})")

    if not _confirm(
        "Back up the database and apply migrations?",
        assume_yes=assume_yes,
    ):
        _warn("Database: skipping migrations at user request.")
        return False

    backup_path = db_base.backup_db()
    if backup_path is None:
        _warn(
            "Database: backup did not produce a file (see log for cause). "
            "Proceeding with migration anyway — restore manually from an "
            f"earlier backup in {config_manager.DATA_DIR / 'backups'} if needed."
        )
    else:
        _banner(f"Database: backed up to {backup_path}")

    try:
        db_base.stamp_and_migrate()
    except Exception:
        restore_hint = backup_path or config_manager.DATA_DIR / "backups"
        _error(
            f"Database: migration failed. The database may be in a partial "
            f"state — restore from {restore_hint} before retrying."
        )
        log.exception("Database: migration failed")
        return False

    _banner("Database: migrations complete.")
    return True


def run_update(args, *, repo_root: Path) -> bool:
    """Entry point for `./ps-empire update`. Moves the Empire checkout to the
    latest release tag, overwrites the base `config.yaml` from the shipped
    template, then refreshes Starkiller / Empire-Compiler / plugin registries
    according to the (possibly just-overwritten) active config.

    Returns True if every step succeeded, False otherwise — caller should
    map this to a process exit code so CI / scripted callers can detect a
    failed update.
    """
    if not check_no_foreign_ownership():
        return False

    assume_yes = getattr(args, "yes", False)

    source_ok = update_empire_source(repo_root)
    if not source_ok:
        _warn(
            "Continuing with the update despite source step failure; the "
            "config overwrite and downstream refreshes will use the existing "
            "local template."
        )

    config_ok = overwrite_base_config(repo_root)
    if config_ok:
        # Reload so the update_* helpers operate on whatever refs the new
        # base config (merged with the user's config.user.yaml) resolves to.
        config_manager.empire_config = config_manager.EmpireConfig()

    results = [
        ("Empire source", source_ok),
        ("Config", config_ok),
        # Run migrations after source/config but before the downstream
        # refreshes so that (a) any new migration scripts pulled in by the
        # source step are on disk, and (b) the user sees the DB step's
        # prompt up-front rather than after sitting through Starkiller /
        # Compiler downloads.
        ("Database", update_database(assume_yes=assume_yes)),
        (
            "Starkiller",
            update_starkiller(
                config_manager.empire_config.starkiller, assume_yes=assume_yes
            ),
        ),
        (
            "Empire Compiler",
            update_empire_compiler(
                config_manager.empire_config.empire_compiler, assume_yes=assume_yes
            ),
        ),
    ]
    for registry in config_manager.empire_config.plugin_marketplace.registries:
        results.append(
            (
                f"Plugin Registry '{registry.name}'",
                update_plugin_registry(registry, assume_yes=assume_yes),
            )
        )

    failed = [label for label, ok in results if not ok]
    if failed:
        _warn(
            f"Update finished with {len(failed)} failure(s): {', '.join(failed)}. "
            "Review the errors above and re-run './ps-empire update' after "
            "resolving them."
        )
        return False

    print(
        "\x1b[1;32m[*] Update complete. Restart the server for changes to take effect.\x1b[0m",
        flush=True,
    )
    return True


def run_setup(args) -> dict[str, bool] | None:
    """Entry point for `./ps-empire setup`. Runs the install-time syncs
    (`sync_starkiller` / `sync_empire_compiler` / `sync_plugin_registry`)
    with banner-style error handling, returning a per-step result dict.

    Symmetric with `run_update`: the same defect class (silent sync
    failures) was fixed there for the `update` subcommand in PR #1276;
    this is its install-time counterpart. Without it, a `setup` run with
    e.g. a blocked GitHub egress prints nothing about the failure and
    crashes the next server boot when `DotnetCompiler.__init__` divides
    `None` by a string.

    Aggregate-then-exit semantics (matching `run_update`): every sync
    runs even after earlier ones fail, so a fresh-install operator sees
    the full list of red banners in one pass. The typical root cause —
    firewall blocking GitHub, missing SSH key for the sponsors repos,
    DNS broken in the install container — breaks several syncs at once,
    and listing them together is more useful than iterative fail-fast.

    Returns:
      - `None` if the foreign-ownership pre-flight failed (caller must
        exit non-zero without doing further work).
      - dict mapping step labels (`"Starkiller"`, `"Empire Compiler"`,
        `"Plugin Registry '<name>'"`) to bool success otherwise.

    The caller (`empire.py`) inspects the dict to gate
    `_auto_install_plugins` on every plugin-registry step succeeding —
    auto-install reads the registry data those syncs populate, so
    running it after a partial sync silently produces an incomplete
    install.
    """
    if not check_no_foreign_ownership():
        return None

    results: dict[str, bool] = {}

    _banner("Starkiller: syncing")
    try:
        sync_starkiller(config_manager.empire_config.starkiller)
        results["Starkiller"] = True
    except GitOperationException as e:
        _error(f"Starkiller: clone failed ({e}).")
        results["Starkiller"] = False

    _banner("Empire Compiler: syncing")
    # Mirrors the failure model in update_empire_compiler:
    # sync_empire_compiler returns None (without raising) for unsupported
    # OS/arch, missing repo/ref config, GitHub API non-OK, or no asset
    # matching the resolved platform — and raises on network / disk /
    # extract failures. Funnel both into a single error path so the
    # banner is uniform regardless of which surface failed.
    error_detail: str | None = None
    try:
        result = sync_empire_compiler(config_manager.empire_config.empire_compiler)
    except (requests.RequestException, tarfile.TarError, OSError) as e:
        error_detail = f"download/extract failed ({e})."
    else:
        if result is None:
            error_detail = (
                "sync returned no path (unsupported platform, missing asset, "
                "or API failure). Check the server log for the underlying cause."
            )
    if error_detail:
        _error(f"Empire Compiler: {error_detail}")
        results["Empire Compiler"] = False
    else:
        results["Empire Compiler"] = True

    for registry in config_manager.empire_config.plugin_marketplace.registries:
        label = f"Plugin Registry '{registry.name}'"
        _banner(f"{label}: syncing")
        try:
            sync_plugin_registry(registry)
            results[label] = True
        except GitOperationException as e:
            _error(f"{label}: clone failed ({e}).")
            results[label] = False

    failed = [label for label, ok in results.items() if not ok]
    if failed:
        _warn(
            f"Setup finished with {len(failed)} failure(s): {', '.join(failed)}. "
            "Resolve the errors above and re-run './ps-empire setup'."
        )

    return results


def sync_plugin_registry(registry_config: PluginRegistryConfig):
    base_dir = config_manager.DATA_DIR / "plugin-registries" / registry_config.name
    base_dir.mkdir(parents=True, exist_ok=True)

    # If a local location is provided, prefer it as-is (no copy) for speed
    if registry_config.location:
        return registry_config.location

    # Clone a git-based registry into a persistent offline directory
    if registry_config.git_url:
        ref = registry_config.ref or "main"
        target_dir = base_dir / ref

        if not target_dir.exists():
            log.info(
                f"Plugin Registry: directory not found for {registry_config.name}. Cloning {registry_config.git_url} ({ref})"
            )
            clone_git_repo(registry_config.git_url, ref, target_dir)

        return target_dir / (registry_config.file or "registry.yaml")

    # Fallback: download from URL and cache to disk for offline use
    if registry_config.url:
        registry_file = base_dir / "registry.yaml"
        log.info(
            f"Plugin Registry: downloading {registry_config.name} from {registry_config.url}"
        )
        resp = requests.get(registry_config.url, timeout=30)
        if resp.ok:
            registry_file.write_text(resp.text)
            return registry_file
        log.error(
            f"Failed to download plugin registry {registry_config.name} from {registry_config.url}"
        )
        return None

    return None
