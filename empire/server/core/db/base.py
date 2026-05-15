import logging
import sqlite3
import stat
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

from sqlalchemy import Index, UniqueConstraint, create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import close_all_sessions, sessionmaker
from sqlalchemy.pool import Pool, QueuePool

from empire.server.core.db import models
from empire.server.core.db.defaults import (
    get_default_config,
    get_default_ips,
    get_default_keyword_obfuscation,
    get_default_obfuscation_config,
    get_default_user,
)
from empire.server.core.db.models import Base, get_database_config

log = logging.getLogger(__name__)


# https://stackoverflow.com/a/13719230
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if type(dbapi_connection) is sqlite3.Connection:  # play well with other DB backends
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.close()


def try_create_engine(engine_url: str, *args, **kwargs) -> Engine:
    engine = create_engine(engine_url, *args, **kwargs)
    try:
        with engine.connect():
            pass
    except OperationalError as e:
        log.error(e, exc_info=True)
        log.error(f"Failed connecting to database using {engine_url}")
        log.error("Perhaps the MySQL service is not running.")
        log.error("Try executing: sudo systemctl start mysql")
        sys.exit(1)

    return engine


use, database_config = get_database_config()


def reset_db():
    close_all_sessions()

    if use == "mysql":
        cmd = f"DROP DATABASE IF EXISTS {database_config.database_name}"
        reset_engine = try_create_engine(mysql_url, echo=False)
        with reset_engine.connect() as connection:
            connection.execute(text(cmd))

    if use == "sqlite":
        Path(database_config.location).unlink(missing_ok=True)


if use == "mysql":
    url = database_config.url
    database_name = database_config.database_name
    encoded_username = (
        quote_plus(database_config.username) if database_config.username else ""
    )
    encoded_password = (
        quote_plus(database_config.password) if database_config.password else ""
    )

    if encoded_username and encoded_password:
        userinfo = f"{encoded_username}:{encoded_password}"
    elif encoded_username:
        userinfo = encoded_username
    else:
        userinfo = ""
    auth = f"{userinfo}@" if userinfo else ""

    mysql_url = f"mysql+pymysql://{auth}{url}"
    engine = try_create_engine(mysql_url, echo=False)
    with engine.connect() as connection:
        connection.execute(text(f"CREATE DATABASE IF NOT EXISTS {database_name}"))
    engine = try_create_engine(
        f"{mysql_url}/{database_name}",
        echo=False,
        pool_size=database_config.pool_size,
        max_overflow=database_config.max_overflow,
        pool_pre_ping=database_config.pool_pre_ping,
        pool_recycle=database_config.pool_recycle,
    )
    log.info(
        "MySQL pool: size=%d, max_overflow=%d, pre_ping=%s, recycle=%ds",
        database_config.pool_size,
        database_config.max_overflow,
        database_config.pool_pre_ping,
        database_config.pool_recycle,
    )
else:
    location = database_config.location
    engine = try_create_engine(
        f"sqlite:///{location}",
        connect_args={
            "check_same_thread": False,
        },
        echo=False,
    )

    models.Host.__table_args__ = (
        UniqueConstraint(
            models.Host.name, models.Host.internal_ip, name="host_unique_idx"
        ),
    )


# ---------------------------------------------------------------------------
# Pool health logging
# ---------------------------------------------------------------------------
_POOL_WARN_THRESHOLD = 0.8  # warn when 80% of pool capacity is in use


@event.listens_for(Pool, "checkout")
def _on_pool_checkout(dbapi_conn, connection_rec, connection_proxy):
    try:
        pool = connection_proxy._pool  # noqa: SLF001
        if not isinstance(pool, QueuePool):
            return
        pool_size = pool.size()
        overflow = pool.overflow()
        max_overflow = pool._max_overflow  # noqa: SLF001
        checked_out = pool.checkedout()
        total_capacity = pool_size + max_overflow
        if total_capacity > 0 and checked_out / total_capacity >= _POOL_WARN_THRESHOLD:
            log.warning(
                "DB pool nearing capacity: %d/%d connections in use "
                "(pool_size=%d, overflow=%d/%d)",
                checked_out,
                total_capacity,
                pool_size,
                overflow,
                max_overflow,
            )
    except Exception:
        log.warning("Pool health check failed — monitoring degraded", exc_info=True)


SessionLocal = sessionmaker(bind=engine)
Base.metadata.create_all(engine)


def _alembic_cfg():
    """Return an Alembic Config pointing at our migrations directory."""
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option(
        "script_location",
        str(Path(__file__).resolve().parent / "alembic"),
    )
    return cfg


def _get_alembic_revision():
    """Return the current Alembic revision, or None if untracked."""
    from alembic.migration import MigrationContext

    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        return ctx.get_current_revision()


def _stamp_alembic_baseline():
    """Stamp the database at the baseline revision (no migrations run).

    Only called for databases that have never been tracked by Alembic.
    """
    from alembic import command

    command.stamp(_alembic_cfg(), "0001")
    log.info("Alembic: stamped database at baseline revision 0001.")


def migrate_db():
    """Run any pending Alembic migrations."""
    from alembic import command

    cfg = _alembic_cfg()
    log.info("Alembic: checking for pending migrations...")
    try:
        command.upgrade(cfg, "head")
        log.info("Alembic: migrations complete.")
    except Exception:
        log.error(
            "Alembic migration failed. Consider restoring from a backup in "
            "~/.local/share/empire/backups/ or running 'server --clean' to reset.",
            exc_info=True,
        )
        raise


def pending_migrations() -> tuple[str | None, str | None]:
    """Return (current_revision, head_revision).

    `current_revision` is None when the database has never been tracked by
    Alembic (i.e. pre-Alembic deployments). `head_revision` is None only if
    the migrations directory contains no revisions, which would indicate a
    broken install.
    """
    from alembic.script import ScriptDirectory

    current = _get_alembic_revision()
    head = ScriptDirectory.from_config(_alembic_cfg()).get_current_head()
    return current, head


def stamp_and_migrate() -> None:
    """Stamp the baseline (if untracked) then run pending migrations.

    Bundles the two-step sequence used by both startup_db() and the
    `update` subcommand so callers don't need to know about the private
    `_stamp_alembic_baseline` helper.
    """
    if _get_alembic_revision() is None:
        _stamp_alembic_baseline()
    migrate_db()


# Modular Crypt Format prefixes for bcrypt. Mirrors the constant in
# `empire.server.api.jwt_auth`, but kept local so this module doesn't
# import jwt_auth (which runs a DB query at module load and would
# break startup_db ordering).
_BCRYPT_HASH_PREFIXES = ("$2a$", "$2b$", "$2x$", "$2y$")


def migrate_legacy_bcrypt_default_user(db) -> bool:
    """If the configured default user still has a bcrypt-shaped password
    hash, reset it to PBKDF2 of the configured default password.

    Bridges operators across PR #1236 (bcrypt → PBKDF2). After the
    auth-code switch, existing bcrypt hashes don't parse and the
    operator can't log in. Auto-recovering only the *configured* default
    user (typically `empireadmin`) keeps the blast radius small: other
    users' rows are untouched and must be reset manually per CHANGELOG.

    Returns True iff a row was rewritten (so callers can surface a
    user-visible confirmation alongside the warning log).
    """
    from empire.server.core.db.defaults import (
        database_config as defaults_config,
    )
    from empire.server.core.db.defaults import (
        get_default_hashed_password,
    )

    default_user = (
        db.query(models.User)
        .filter(models.User.username == defaults_config.username)
        .first()
    )
    if default_user is None:
        return False
    if not (default_user.hashed_password or "").startswith(_BCRYPT_HASH_PREFIXES):
        return False

    default_user.hashed_password = get_default_hashed_password()
    log.warning(
        "Auto-reset: default user '%s' had a legacy bcrypt password hash "
        "(pre-PR-#1236). Rewritten to a PBKDF2 hash of the password in "
        "config (database.defaults.password). Other users with bcrypt "
        "hashes are NOT auto-reset — see CHANGELOG.md for the manual "
        "recovery procedure.",
        defaults_config.username,
    )
    return True


def backup_db() -> Path | None:
    """Back up the database before an update. Returns the backup path or None."""
    from empire.server.core.config.config_manager import DATA_DIR

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = DATA_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    if use == "sqlite":
        src = Path(database_config.location)
        if src.exists():
            dst = backup_dir / f"empire.db.{timestamp}"
            # Use SQLite's backup API for a consistent snapshot even
            # when the database is in WAL mode with active connections.
            try:
                src_conn = sqlite3.connect(str(src))
                dst_conn = sqlite3.connect(str(dst))
                try:
                    src_conn.backup(dst_conn)
                finally:
                    dst_conn.close()
                    src_conn.close()
            except Exception:
                log.error("SQLite backup failed.", exc_info=True)
                dst.unlink(missing_ok=True)
                return None
            log.info(f"SQLite database backed up to {dst}")
            return dst
        log.warning("SQLite database file not found — nothing to back up.")
        return None

    if use == "mysql":
        dst = backup_dir / f"empire_mysql.{timestamp}.sql"
        parts = database_config.url.split(":")
        host = parts[0]

        # Write credentials to a temp file (mode 0600) instead of
        # exposing them on the command line or via environment variables.
        cnf_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".cnf", delete=False
            ) as cnf:
                escaped_pw = database_config.password.replace("\\", "\\\\").replace(
                    '"', '\\"'
                )
                cnf.write(f'[client]\npassword="{escaped_pw}"\n')
                cnf_path = cnf.name
            Path(cnf_path).chmod(stat.S_IRUSR | stat.S_IWUSR)

            cmd = [
                "mysqldump",
                f"--defaults-extra-file={cnf_path}",
                "-u",
                database_config.username,
                "-h",
                host,
            ]
            if len(parts) > 1:
                cmd.extend(["-P", parts[1]])
            cmd.append(database_config.database_name)

            with dst.open("w") as outfile:
                try:
                    result = subprocess.run(
                        cmd,
                        stdout=outfile,
                        stderr=subprocess.PIPE,
                        check=False,
                    )
                except FileNotFoundError:
                    log.error(
                        "mysqldump not found on PATH. Install mysql-client "
                        "to enable MySQL backups."
                    )
                    dst.unlink(missing_ok=True)
                    return None
            if result.returncode == 0:
                log.info(f"MySQL database backed up to {dst}")
                return dst
            log.warning(
                f"MySQL backup failed (exit {result.returncode}): "
                f"{result.stderr.decode(errors='replace')}"
            )
            dst.unlink(missing_ok=True)
        except Exception:
            log.error("MySQL backup failed unexpectedly.", exc_info=True)
            dst.unlink(missing_ok=True)
        finally:
            if cnf_path is not None:
                Path(cnf_path).unlink(missing_ok=True)

        return None

    log.warning(f"Unknown database type '{use}' — cannot back up.")
    return None


def startup_db():
    try:
        with SessionLocal.begin() as db:
            if use == "mysql":
                database_name = database_config.database_name

                result = db.execute(
                    text(
                        f"""
                    SELECT * FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = '{database_name}'
                    AND table_name = 'hosts'
                    AND column_name = 'unique_check'
                    """
                    )
                ).fetchone()
                if not result:
                    db.execute(
                        text(
                            """
                        ALTER TABLE hosts
                        ADD COLUMN unique_check VARCHAR(255) GENERATED ALWAYS AS (SHA2(CONCAT(name, internal_ip), 256)) UNIQUE;
                        """
                        )
                    )

                    # index agent_id and checkin_time together
                    # won't work for sqlite.
                    Index(
                        "agent_checkin_idx",
                        models.AgentCheckIn.agent_id,
                        models.AgentCheckIn.checkin_time.desc(),
                    )

            # When Empire starts up for the first time, it will create the database and create
            # these default records.
            if len(db.query(models.User).all()) == 0:
                log.info("Setting up database.")
                log.info("Adding default user.")
                db.add(get_default_user())

            if len(db.query(models.Config).all()) == 0:
                log.info("Adding database config.")
                db.add(get_default_config())

            if len(db.query(models.Keyword).all()) == 0:
                log.info("Adding default keyword obfuscation functions.")
                keywords = get_default_keyword_obfuscation()

                for keyword in keywords:
                    db.add(keyword)

            if len(db.query(models.ObfuscationConfig).all()) == 0:
                log.info("Adding default obfuscation config.")
                obf_configs = get_default_obfuscation_config()

                for config in obf_configs:
                    db.add(config)

            if len(db.query(models.IP).all()) == 0:
                ips = get_default_ips()

                for ip in ips:
                    db.add(ip)

            # Recover the configured default user across the bcrypt → PBKDF2
            # cutover in PR #1236. No-op for fresh installs (where the row
            # was just inserted above with a PBKDF2 hash) and for upgrades
            # whose default user already has a PBKDF2 hash.
            migrate_legacy_bcrypt_default_user(db)

            # Checking that schema matches the db.
            # Some errors don't manifest until query time.
            for model in models.Base.__subclasses__():
                db.query(model).first()

    except Exception as e:
        log.error(e, exc_info=True)
        log.error("Failed to setup database.")
        log.error(
            "If you have recently updated Empire, please run 'server --clean' to reset the database."
        )
        sys.exit(1)

    # Stamp Alembic baseline for databases not yet tracked by Alembic.
    # Existing tracked databases are left as-is so migrate_db() can
    # apply any pending migrations. Kept outside the DB-setup try/except
    # so that Alembic failures get their own error message instead of the
    # misleading "run --clean" advice.
    try:
        current_rev = _get_alembic_revision()
        if current_rev is None:
            _stamp_alembic_baseline()
        else:
            log.info(
                "Alembic: database already tracked at revision %s.",
                current_rev,
            )
    except Exception:
        log.error(
            "Alembic: failed to initialize migration tracking. "
            "Check that the alembic package is installed and the "
            "migrations directory exists at empire/server/core/db/alembic/.",
            exc_info=True,
        )
        sys.exit(1)
