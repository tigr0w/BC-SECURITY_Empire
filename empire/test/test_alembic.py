"""Tests for Alembic database migration infrastructure."""

import importlib.util
import textwrap
from pathlib import Path

import pytest
from sqlalchemy import inspect, text


def _load_0007_migration():
    """Load the 0007 tags-as-labels migration module by path. Its filename starts
    with a digit, so it can't be imported normally; each call returns a fresh module."""
    from empire.server.core.db.base import _alembic_cfg

    versions_dir = Path(_alembic_cfg().get_main_option("script_location")) / "versions"
    spec = importlib.util.spec_from_file_location(
        "mig_0007", versions_dir / "0007_tags_as_labels.py"
    )
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    return mig


# ---------------------------------------------------------------------------
# Safety net: clean up any stale test migration files on session teardown
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True, scope="session")
def _cleanup_stale_test_migrations():
    """Remove any 0004_test_* migration files left by crashed tests."""
    yield
    from empire.server.core.db.base import _alembic_cfg

    versions_dir = Path(_alembic_cfg().get_main_option("script_location")) / "versions"
    for stale in versions_dir.glob("0004_test_*"):
        stale.unlink(missing_ok=True)
    pycache = versions_dir / "__pycache__"
    if pycache.exists():
        for cached in pycache.glob("0004_test_*"):
            cached.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cleanup_test_migration(migration_file: Path):
    """Remove a test migration file and its __pycache__ bytecode."""
    migration_file.unlink(missing_ok=True)
    pycache_dir = migration_file.parent / "__pycache__"
    if pycache_dir.exists():
        for cached in pycache_dir.glob(f"{migration_file.stem}*"):
            cached.unlink(missing_ok=True)


def _get_alembic_version(session):
    """Read the current alembic_version from the DB."""
    row = session.execute(text("SELECT version_num FROM alembic_version")).fetchone()
    return row[0] if row else None


def _head_revision() -> str:
    """Thin wrapper around the prod helper so test and prod behavior stay in sync."""
    from empire.server.core.db.base import _get_head_revision

    return _get_head_revision()


@pytest.fixture
def _restore_db_to_baseline_after():
    """Reset alembic_version to the startup resting state (baseline 0001)
    after a test mutates it, so version state doesn't leak across the
    session-scoped DB. The physical schema is always at head via create_all;
    only the version row is reset, matching startup_db()'s stamp-only
    behavior (it never auto-migrates to head).
    """
    yield
    from empire.server.core.db.base import SessionLocal, _stamp_alembic_baseline

    with SessionLocal.begin() as session:
        session.execute(text("DROP TABLE IF EXISTS alembic_version"))
    _stamp_alembic_baseline()


def _is_expected_diff(diff_item):
    """Filter out diffs from MySQL-specific columns/indexes managed by startup_db().

    Only suppresses the specific known differences:
    - agent_checkin_idx index (created via startup_db SQL for MySQL)
    - host_unique_idx constraint (created via SQLite table args)
    - unique_check generated column (MySQL-only, not in models)
    """
    if not isinstance(diff_item, tuple):
        return False

    op_type = diff_item[0]

    # agent_checkin_idx: created manually in startup_db for MySQL
    # unique_check: unique index on the MySQL generated column
    if op_type in ("add_index", "remove_index"):
        idx = diff_item[1] if len(diff_item) > 1 else None
        return getattr(idx, "name", None) in ("agent_checkin_idx", "unique_check")

    # host_unique_idx: managed via Host.__table_args__ for SQLite
    if op_type in ("add_constraint", "remove_constraint"):
        constraint = diff_item[1] if len(diff_item) > 1 else None
        return getattr(constraint, "name", None) == "host_unique_idx"

    # unique_check: MySQL generated column added by startup_db SQL
    if op_type in ("add_column", "remove_column"):
        col = diff_item[-1]
        return getattr(col, "name", None) == "unique_check"

    return False


# ---------------------------------------------------------------------------
# Basic infrastructure tests
# ---------------------------------------------------------------------------


def test_alembic_cfg_valid():
    """_alembic_cfg() returns a Config whose script_location exists."""
    from empire.server.core.db.base import _alembic_cfg

    cfg = _alembic_cfg()
    script_dir = Path(cfg.get_main_option("script_location"))
    assert script_dir.exists()
    assert (script_dir / "env.py").exists()
    assert (script_dir / "versions").is_dir()


def test_alembic_version_table_exists(client):
    """After startup_db(), the alembic_version table should exist at revision 0001."""
    from empire.server.core.db.base import SessionLocal

    with SessionLocal() as session:
        insp = inspect(session.bind)
        assert "alembic_version" in insp.get_table_names()
        assert _get_alembic_version(session) == "0001"


@pytest.mark.usefixtures("_restore_db_to_baseline_after")
def test_migrate_db_noop(client):
    """migrate_db() completes without error and leaves the DB at head."""
    from empire.server.core.db.base import SessionLocal, migrate_db

    migrate_db()

    with SessionLocal() as session:
        assert _get_alembic_version(session) == _head_revision()


def test_stamp_idempotent(client):
    """Calling _stamp_alembic_baseline() twice doesn't raise and keeps version at 0001."""
    from empire.server.core.db.base import SessionLocal, _stamp_alembic_baseline

    _stamp_alembic_baseline()
    _stamp_alembic_baseline()

    with SessionLocal() as session:
        assert _get_alembic_version(session) == "0001"


def test_autogenerate_no_diff(client):
    """Alembic autogenerate should detect no schema differences."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from empire.server.core.db.base import SessionLocal
    from empire.server.core.db.models import Base

    with SessionLocal() as session:
        mc = MigrationContext.configure(session.connection())
        diff = compare_metadata(mc, Base.metadata)

    meaningful_diffs = [d for d in diff if not _is_expected_diff(d)]
    assert meaningful_diffs == [], f"Unexpected schema diffs: {meaningful_diffs}"


# ---------------------------------------------------------------------------
# Backup tests
# ---------------------------------------------------------------------------


def test_backup_db_sqlite(client):
    """backup_db() creates a non-empty SQLite backup file."""
    from empire.server.core.db.base import backup_db
    from empire.server.core.db.models import get_database_config

    db_use, _ = get_database_config()
    if db_use != "sqlite":
        pytest.skip("SQLite-only test")

    result = backup_db()
    assert result is not None
    assert result.exists()
    assert result.stat().st_size > 0

    result.unlink(missing_ok=True)


@pytest.mark.usefixtures("_restore_db_to_baseline_after")
def test_backup_then_migrate_sqlite(client):
    """Full backup-then-migrate workflow: backup succeeds, migrate reaches head, DB intact."""
    from empire.server.core.db.base import SessionLocal, backup_db, migrate_db
    from empire.server.core.db.models import get_database_config

    db_use, _ = get_database_config()
    if db_use != "sqlite":
        pytest.skip("SQLite-only test")

    # Record row count before
    with SessionLocal() as session:
        user_count_before = session.execute(text("SELECT count(*) FROM users")).scalar()

    backup_path = backup_db()
    assert backup_path is not None

    migrate_db()

    # Verify DB is still intact after migrate
    with SessionLocal() as session:
        user_count_after = session.execute(text("SELECT count(*) FROM users")).scalar()
        assert user_count_after == user_count_before
        assert _get_alembic_version(session) == _head_revision()

    backup_path.unlink(missing_ok=True)


def test_backup_db_sqlite_missing_file(client, tmp_path, monkeypatch):
    """backup_db() returns None when SQLite file doesn't exist."""
    from empire.server.core.db import base as base_mod
    from empire.server.core.db.models import get_database_config

    db_use, _ = get_database_config()
    if db_use != "sqlite":
        pytest.skip("SQLite-only test")

    # Monkeypatch database_config.location to a non-existent path
    import types

    fake_config = types.SimpleNamespace(location=str(tmp_path / "nonexistent.db"))
    monkeypatch.setattr(base_mod, "database_config", fake_config)

    result = base_mod.backup_db()
    assert result is None


# ---------------------------------------------------------------------------
# Pre-Alembic upgrade path (existing DB without alembic_version)
# ---------------------------------------------------------------------------


def test_stamp_on_pre_alembic_db(client):
    """Simulate a pre-Alembic database: drop alembic_version, re-stamp, verify."""
    from empire.server.core.db.base import SessionLocal, _stamp_alembic_baseline

    # Drop the alembic_version table to simulate a pre-Alembic DB
    with SessionLocal.begin() as session:
        session.execute(text("DROP TABLE IF EXISTS alembic_version"))

    # Verify it's gone
    with SessionLocal() as session:
        insp = inspect(session.bind)
        assert "alembic_version" not in insp.get_table_names()

    # Re-stamp (this is what startup_db() does on existing deployments)
    _stamp_alembic_baseline()

    # Verify it's back and at the right revision
    with SessionLocal() as session:
        insp = inspect(session.bind)
        assert "alembic_version" in insp.get_table_names()
        assert _get_alembic_version(session) == "0001"


@pytest.mark.usefixtures("_restore_db_to_baseline_after")
def test_migrate_on_pre_alembic_db(client):
    """Simulate upgrading a pre-Alembic DB: drop version table, then migrate_db()."""
    from empire.server.core.db.base import (
        SessionLocal,
        _stamp_alembic_baseline,
        migrate_db,
    )

    # Drop alembic_version to simulate pre-Alembic state
    with SessionLocal.begin() as session:
        session.execute(text("DROP TABLE IF EXISTS alembic_version"))

    # Stamp baseline first (as startup_db would), then migrate to head
    _stamp_alembic_baseline()
    migrate_db()

    with SessionLocal() as session:
        assert _get_alembic_version(session) == _head_revision()


# ---------------------------------------------------------------------------
# Real migration: create, apply, verify, downgrade
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_restore_db_to_baseline_after")
def test_real_migration_add_and_remove_column(client):
    """Create a real migration that adds a column, apply it, verify, then downgrade."""
    from alembic import command

    from empire.server.core.db.base import SessionLocal, _alembic_cfg

    cfg = _alembic_cfg()
    versions_dir = Path(cfg.get_main_option("script_location")) / "versions"

    # Chain the throwaway fixture off the real head with a unique revision id
    # so it never collides with the shipped 0002 migration.
    head = _head_revision()
    test_rev = "0002_test_add_column"

    # Write a migration file that adds a test column to the 'users' table
    migration_file = versions_dir / "0004_test_add_column.py"
    migration_file.write_text(
        textwrap.dedent("""\
        \"\"\"test add column

        Revision ID: {rev}
        Revises: {down}
        Create Date: 2026-03-25
        \"\"\"
        from collections.abc import Sequence

        import sqlalchemy as sa
        from alembic import op

        revision: str = "{rev}"
        down_revision: str | None = "{down}"
        branch_labels: str | Sequence[str] | None = None
        depends_on: str | Sequence[str] | None = None


        def upgrade() -> None:
            op.add_column("users", sa.Column("_alembic_test", sa.String(50), nullable=True))


        def downgrade() -> None:
            op.drop_column("users", "_alembic_test")
        """).format(rev=test_rev, down=head)
    )

    try:
        # Apply the migration
        command.upgrade(cfg, "head")

        # Verify the column was added
        with SessionLocal() as session:
            insp = inspect(session.bind)
            columns = [c["name"] for c in insp.get_columns("users")]
            assert "_alembic_test" in columns
            assert _get_alembic_version(session) == test_rev

        # Downgrade back to the shipped head
        command.downgrade(cfg, head)

        # Verify the column was removed
        with SessionLocal() as session:
            insp = inspect(session.bind)
            columns = [c["name"] for c in insp.get_columns("users")]
            assert "_alembic_test" not in columns
            assert _get_alembic_version(session) == head

    finally:
        # Clean up the test migration file
        _cleanup_test_migration(migration_file)


@pytest.mark.usefixtures("_restore_db_to_baseline_after")
def test_migrate_db_applies_pending_migration(client):
    """migrate_db() picks up and applies a new migration file."""
    from empire.server.core.db.base import SessionLocal, _alembic_cfg, migrate_db

    cfg = _alembic_cfg()
    versions_dir = Path(cfg.get_main_option("script_location")) / "versions"

    # Chain off the real head with a unique revision id (no collision with 0002).
    head = _head_revision()
    test_rev = "0002_test_pending"

    migration_file = versions_dir / "0004_test_pending.py"
    migration_file.write_text(
        textwrap.dedent("""\
        \"\"\"test pending migration

        Revision ID: {rev}
        Revises: {down}
        Create Date: 2026-03-25
        \"\"\"
        from collections.abc import Sequence

        import sqlalchemy as sa
        from alembic import op

        revision: str = "{rev}"
        down_revision: str | None = "{down}"
        branch_labels: str | Sequence[str] | None = None
        depends_on: str | Sequence[str] | None = None


        def upgrade() -> None:
            op.add_column("users", sa.Column("_alembic_pending_test", sa.String(50), nullable=True))


        def downgrade() -> None:
            op.drop_column("users", "_alembic_pending_test")
        """).format(rev=test_rev, down=head)
    )

    try:
        # Use migrate_db() (the public API) instead of command.upgrade directly
        migrate_db()

        with SessionLocal() as session:
            insp = inspect(session.bind)
            columns = [c["name"] for c in insp.get_columns("users")]
            assert "_alembic_pending_test" in columns
            assert _get_alembic_version(session) == test_rev

        # Clean up: downgrade back to the shipped head
        from alembic import command

        command.downgrade(cfg, head)

        with SessionLocal() as session:
            insp = inspect(session.bind)
            columns = [c["name"] for c in insp.get_columns("users")]
            assert "_alembic_pending_test" not in columns

    finally:
        _cleanup_test_migration(migration_file)


@pytest.mark.usefixtures("_restore_db_to_baseline_after")
def test_failed_migration_does_not_corrupt_version(client):
    """A migration that raises an error should not advance the version past the last good revision."""
    from empire.server.core.db.base import SessionLocal, _alembic_cfg, migrate_db

    cfg = _alembic_cfg()
    versions_dir = Path(cfg.get_main_option("script_location")) / "versions"

    # Chain the broken fixture off the real head with a unique revision id.
    # The shipped head applies cleanly first; the broken fixture then fails,
    # so the version must remain at the last good revision (the real head).
    head = _head_revision()
    test_rev = "0002_test_broken"

    migration_file = versions_dir / "0004_test_broken.py"
    migration_file.write_text(
        textwrap.dedent("""\
        \"\"\"broken migration

        Revision ID: {rev}
        Revises: {down}
        Create Date: 2026-03-25
        \"\"\"
        from collections.abc import Sequence

        from alembic import op

        revision: str = "{rev}"
        down_revision: str | None = "{down}"
        branch_labels: str | Sequence[str] | None = None
        depends_on: str | Sequence[str] | None = None


        def upgrade() -> None:
            # This will fail: table doesn't exist
            op.drop_table("this_table_does_not_exist_at_all")


        def downgrade() -> None:
            pass
        """).format(rev=test_rev, down=head)
    )

    try:
        with pytest.raises(Exception, match="this_table_does_not_exist_at_all"):
            migrate_db()

        # Version should remain at the last good revision (the shipped head),
        # not advance to the broken fixture.
        with SessionLocal() as session:
            assert _get_alembic_version(session) == head

    finally:
        _cleanup_test_migration(migration_file)


# ---------------------------------------------------------------------------
# Fresh database from scratch
# ---------------------------------------------------------------------------


def test_fresh_db_has_all_tables(tmp_path):
    """create_all on an empty DB produces all expected tables."""
    from sqlalchemy import create_engine

    from empire.server.core.db.models import Base

    db_path = tmp_path / "fresh_test.db"
    fresh_engine = create_engine(f"sqlite:///{db_path}", echo=False)
    Base.metadata.create_all(fresh_engine)

    insp = inspect(fresh_engine)
    tables = insp.get_table_names()
    for expected in ("users", "agents", "listeners", "hosts", "credentials"):
        assert expected in tables, f"Missing table: {expected}"

    fresh_engine.dispose()


@pytest.mark.usefixtures("_restore_db_to_baseline_after")
def test_stamp_then_migrate_consistent(client):
    """After stamp + migrate, DB should be at head with all tables intact."""
    from empire.server.core.db.base import (
        SessionLocal,
        _stamp_alembic_baseline,
        migrate_db,
    )

    # Drop and re-stamp to simulate the full startup flow
    with SessionLocal.begin() as session:
        session.execute(text("DROP TABLE IF EXISTS alembic_version"))

    _stamp_alembic_baseline()
    migrate_db()

    with SessionLocal() as session:
        assert _get_alembic_version(session) == _head_revision()

        # Verify core tables still exist
        insp = inspect(session.bind)
        tables = insp.get_table_names()
        assert "users" in tables
        assert "agents" in tables
        assert "listeners" in tables


def test_migrate_legacy_bcrypt_default_user_resets(client):
    """A bcrypt-shaped hash on the configured default user gets auto-reset
    to PBKDF2(default_password). Verifies the auth flow that recovers an
    operator who upgraded across PR #1236.
    """
    import logging

    from empire.server.api.jwt_auth import verify_password
    from empire.server.core.db import models
    from empire.server.core.db.base import (
        SessionLocal,
        migrate_legacy_bcrypt_default_user,
    )
    from empire.server.core.db.defaults import database_config as defaults_config

    bcrypt_hash = "$2b$12$LJ3m4ys3LfDLqMEnOaaFreFEHrWdEFmSHOuDKLmmkbLhLmKCuby4q"

    # Plant a fake bcrypt hash on the default user.
    with SessionLocal.begin() as db:
        u = (
            db.query(models.User)
            .filter(models.User.username == defaults_config.username)
            .first()
        )
        original_hash = u.hashed_password
        u.hashed_password = bcrypt_hash

    try:
        # Run the migrator and capture the WARNING log.
        with SessionLocal.begin() as db:
            logger = logging.getLogger("empire.server.core.db.base")
            records: list[logging.LogRecord] = []
            handler = logging.Handler()
            handler.emit = records.append  # type: ignore[assignment]
            handler.setLevel(logging.WARNING)
            logger.addHandler(handler)
            try:
                assert migrate_legacy_bcrypt_default_user(db) is True
            finally:
                logger.removeHandler(handler)

        assert any(
            "Auto-reset" in rec.getMessage() and "PR-#1236" in rec.getMessage()
            for rec in records
        ), "Expected a WARNING log naming the auto-reset and PR-#1236"

        # Hash on disk must now verify against the configured default
        # password and look like a PBKDF2 hash, not bcrypt.
        with SessionLocal() as db:
            u = (
                db.query(models.User)
                .filter(models.User.username == defaults_config.username)
                .first()
            )
            assert u.hashed_password.startswith("pbkdf2:sha256:")
            assert verify_password(defaults_config.password, u.hashed_password)
    finally:
        # Restore for any later tests in the session.
        with SessionLocal.begin() as db:
            u = (
                db.query(models.User)
                .filter(models.User.username == defaults_config.username)
                .first()
            )
            u.hashed_password = original_hash


def test_migrate_legacy_bcrypt_default_user_noop_when_already_pbkdf2(client):
    """If the default user's hash is already PBKDF2, the migrator is a no-op."""
    from empire.server.core.db import models
    from empire.server.core.db.base import (
        SessionLocal,
        migrate_legacy_bcrypt_default_user,
    )
    from empire.server.core.db.defaults import database_config as defaults_config

    with SessionLocal.begin() as db:
        u_before = (
            db.query(models.User)
            .filter(models.User.username == defaults_config.username)
            .first()
        )
        assert u_before.hashed_password.startswith("pbkdf2:")
        before = u_before.hashed_password

        assert migrate_legacy_bcrypt_default_user(db) is False

        u_after = (
            db.query(models.User)
            .filter(models.User.username == defaults_config.username)
            .first()
        )
        assert u_after.hashed_password == before


def test_migrate_legacy_bcrypt_does_not_touch_non_default_user(client):
    """Non-default users with bcrypt hashes are left alone — operator must
    reset those manually so the auto-recovery can't be used as a privilege
    escalation vector via DB tampering.
    """
    from empire.server.core.db import models
    from empire.server.core.db.base import (
        SessionLocal,
        migrate_legacy_bcrypt_default_user,
    )

    bcrypt_hash = "$2b$12$LJ3m4ys3LfDLqMEnOaaFreFEHrWdEFmSHOuDKLmmkbLhLmKCuby4q"
    extra_username = "not_the_default_user_for_bcrypt_test"

    with SessionLocal.begin() as db:
        db.add(
            models.User(
                username=extra_username,
                hashed_password=bcrypt_hash,
                enabled=True,
                admin=False,
            )
        )

    try:
        with SessionLocal.begin() as db:
            # Migrator targets only the configured default user.
            migrate_legacy_bcrypt_default_user(db)

        with SessionLocal() as db:
            u = (
                db.query(models.User)
                .filter(models.User.username == extra_username)
                .first()
            )
            assert u.hashed_password == bcrypt_hash, (
                "Non-default user's bcrypt hash must not be auto-rewritten"
            )
    finally:
        with SessionLocal.begin() as db:
            db.query(models.User).filter(
                models.User.username == extra_username
            ).delete()


def test_startup_does_not_restamp_tracked_db(client):
    """startup_db only stamps untracked databases; already-tracked DBs keep their revision."""
    from empire.server.core.db.base import SessionLocal, _get_alembic_revision

    # DB should already be tracked from the test session's startup_db()
    current = _get_alembic_revision()
    assert current is not None, "DB should be tracked by Alembic after startup"

    # Verify the revision is consistent across calls (startup doesn't reset it)
    with SessionLocal() as session:
        assert _get_alembic_version(session) == current


# ---------------------------------------------------------------------------
# MySQL backup mock tests
# ---------------------------------------------------------------------------


def test_backup_db_mysql_success(client, tmp_path, monkeypatch):
    """backup_db() with MySQL uses --defaults-extra-file and cleans up cnf."""
    import types

    from empire.server.core.db import base as base_mod

    fake_config = types.SimpleNamespace(
        url="localhost:3306",
        username="empire_user",
        password="s3cr#t",
        database_name="empire",
    )
    monkeypatch.setattr(base_mod, "use", "mysql")
    monkeypatch.setattr(base_mod, "database_config", fake_config)
    monkeypatch.setattr("empire.server.core.config.config_manager.DATA_DIR", tmp_path)

    captured_cmd = []
    cnf_files_seen = []

    def mock_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        # Capture the cnf file path and verify it exists during the call
        for arg in cmd:
            if arg.startswith("--defaults-extra-file="):
                cnf_file = Path(arg.split("=", 1)[1])
                cnf_files_seen.append(cnf_file)
                assert cnf_file.exists(), "cnf file should exist during subprocess"
                content = cnf_file.read_text()
                assert "s3cr#t" in content, "cnf should contain the password"
                # Verify mode is 0600
                owner_rw_only = 0o600
                assert cnf_file.stat().st_mode & 0o777 == owner_rw_only
        stdout = kwargs.get("stdout")
        if stdout:
            stdout.write("-- MySQL dump\nCREATE TABLE users;\n")
        return types.SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr("subprocess.run", mock_run)

    result = base_mod.backup_db()
    assert result is not None
    assert result.exists()
    assert "MySQL dump" in result.read_text()

    # Verify --defaults-extra-file was used (not -p or MYSQL_PWD)
    assert any(arg.startswith("--defaults-extra-file=") for arg in captured_cmd), (
        "Should use --defaults-extra-file"
    )
    assert not any(arg.startswith("-p") and arg != "-P" for arg in captured_cmd), (
        "Password should not appear on command line"
    )

    # Verify cnf file was cleaned up after the call
    assert len(cnf_files_seen) == 1
    assert not cnf_files_seen[0].exists(), "cnf file should be cleaned up"

    result.unlink(missing_ok=True)


def test_backup_db_mysql_dump_failure(client, tmp_path, monkeypatch):
    """backup_db() cleans up partial file and returns None on mysqldump failure."""
    import types

    from empire.server.core.db import base as base_mod

    fake_config = types.SimpleNamespace(
        url="localhost:3306",
        username="empire_user",
        password="secret",
        database_name="empire",
    )
    monkeypatch.setattr(base_mod, "use", "mysql")
    monkeypatch.setattr(base_mod, "database_config", fake_config)
    monkeypatch.setattr("empire.server.core.config.config_manager.DATA_DIR", tmp_path)

    def mock_run(cmd, **kwargs):
        return types.SimpleNamespace(returncode=2, stderr=b"Access denied")

    monkeypatch.setattr("subprocess.run", mock_run)

    result = base_mod.backup_db()
    assert result is None

    # Verify no partial file left behind
    backup_dir = tmp_path / "backups"
    if backup_dir.exists():
        sql_files = list(backup_dir.glob("*.sql"))
        assert len(sql_files) == 0, "Partial backup file was not cleaned up"


def test_backup_db_mysql_missing_mysqldump(client, tmp_path, monkeypatch):
    """backup_db() handles missing mysqldump binary gracefully."""
    import types

    from empire.server.core.db import base as base_mod

    fake_config = types.SimpleNamespace(
        url="localhost:3306",
        username="empire_user",
        password="secret",
        database_name="empire",
    )
    monkeypatch.setattr(base_mod, "use", "mysql")
    monkeypatch.setattr(base_mod, "database_config", fake_config)
    monkeypatch.setattr("empire.server.core.config.config_manager.DATA_DIR", tmp_path)

    def mock_run(cmd, **kwargs):
        raise FileNotFoundError("mysqldump not found")

    monkeypatch.setattr("subprocess.run", mock_run)

    result = base_mod.backup_db()
    assert result is None


def test_backup_db_unknown_type(client, tmp_path, monkeypatch):
    """backup_db() returns None and logs warning for unknown DB type."""
    from empire.server.core.db import base as base_mod

    monkeypatch.setattr(base_mod, "use", "postgres")
    monkeypatch.setattr("empire.server.core.config.config_manager.DATA_DIR", tmp_path)

    result = base_mod.backup_db()
    assert result is None


def test_backup_db_mysql_port_parsing(client, tmp_path, monkeypatch):
    """backup_db() correctly parses host and port from MySQL URL."""
    import types

    from empire.server.core.db import base as base_mod

    fake_config = types.SimpleNamespace(
        url="db.example.com:3307",
        username="user",
        password="pass",
        database_name="mydb",
    )
    monkeypatch.setattr(base_mod, "use", "mysql")
    monkeypatch.setattr(base_mod, "database_config", fake_config)
    monkeypatch.setattr("empire.server.core.config.config_manager.DATA_DIR", tmp_path)

    captured_cmd = []

    def mock_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        stdout = kwargs.get("stdout")
        if stdout:
            stdout.write("-- dump\n")
        return types.SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr("subprocess.run", mock_run)

    result = base_mod.backup_db()
    assert result is not None

    # Verify -h, -P, and --defaults-extra-file flags
    assert "-h" in captured_cmd
    h_idx = captured_cmd.index("-h")
    assert captured_cmd[h_idx + 1] == "db.example.com"

    assert "-P" in captured_cmd
    p_idx = captured_cmd.index("-P")
    assert captured_cmd[p_idx + 1] == "3307"

    # A specified port must force TCP, otherwise the MySQL client special-cases
    # `-h localhost` and falls back to the Unix socket (ignoring `-P`).
    assert "--protocol=tcp" in captured_cmd

    assert any(arg.startswith("--defaults-extra-file=") for arg in captured_cmd)

    result.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Migration 0007: fold tags
# ---------------------------------------------------------------------------


def test_fold_tags_migration_is_idempotent_and_dedupes(tmp_path):
    """The 0007 fold is row-level idempotent and folds name:value -> name."""
    from sqlalchemy import create_engine, text

    mig = _load_0007_migration()

    # Build a tiny OLD-shape tags table + one association table in a temp SQLite DB.
    engine = create_engine(f"sqlite:///{tmp_path}/old.db")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE tags (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
                "value TEXT NOT NULL, color TEXT)"
            )
        )
        conn.execute(
            text("CREATE TABLE download_tag_assc (download_id INTEGER, tag_id INTEGER)")
        )
        # Two rows folding to the SAME label, plus a case-variant, plus task:input.
        conn.execute(
            text(
                "INSERT INTO tags (id, name, value, color) VALUES "
                "(1, 'os', 'windows', NULL), (2, 'os', 'windows', '#abc123'), "
                "(3, 'OS', 'Windows', NULL), (4, 'task', 'input', NULL)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO download_tag_assc (download_id, tag_id) VALUES "
                "(10, 1), (10, 2), (11, 3), (12, 4)"
            )
        )

    with engine.begin() as conn:
        mig._fold_tags(conn)
        # Re-run to prove no double-fold.
        mig._fold_tags(conn)

    with engine.connect() as conn:
        names = sorted(r[0] for r in conn.execute(text("SELECT name FROM tags")))
        # os:windows collapsed to one survivor (case-insensitive), task:input folded.
        assert names == ["os:windows", "task:input"]
        # No double-fold:
        assert "os:windows:windows" not in names
        assert "task:input:input" not in names
        # All download associations rewired to surviving tag ids and deduped.
        rows = conn.execute(
            text(
                "SELECT download_id, tag_id FROM download_tag_assc ORDER BY download_id"
            )
        ).all()
        tag_ids = {r[1] for r in rows}
        assert tag_ids.issubset(
            {r[0] for r in conn.execute(text("SELECT id FROM tags"))}
        )
        # The duplicated (10, survivor) association row was deduped to one.
        assert len(rows) == 3  # noqa: PLR2004


def test_fold_name_sql_is_dialect_aware():
    """The fold concat MUST use CONCAT on MySQL — `||` there is logical OR, not
    string concatenation, and would rewrite every tag name to a number."""
    mig = _load_0007_migration()

    assert mig._fold_name_sql("mysql") == "CONCAT(name, ':', value)"
    assert mig._fold_name_sql("sqlite") == "name || ':' || value"


def test_0007_frozen_copies_match_live_source():
    """0007 deliberately FREEZES copies of two things it cannot import from live
    code (migrations must be stable): the color helper and the association-table
    list. Guard against silent drift — if the live source changes, these assertions
    flag that the frozen copies (and the back-compat fold they drive) need review."""
    from empire.server.core.db import models
    from empire.server.core.tag_service import color_from_name

    mig = _load_0007_migration()

    for name in ("prod", "os:windows", "task:input", "Staging-2"):
        assert mig._color_from_name(name) == color_from_name(name), (
            f"0007._color_from_name diverged from tag_service.color_from_name for {name!r}"
        )

    # Subset, not equality: 0007 is frozen to the six tables that existed at 7.0, so
    # a LATER migration adding a 7th taggable table (which 0007 needn't fold) must
    # not fail this. The invariant is that every table 0007 references still exists.
    assert set(mig._ASSC_TABLES) <= {t.name for t in models.all_tag_assc_tables}, (
        "0007._ASSC_TABLES references an association table that no longer exists in "
        "models.all_tag_assc_tables — the frozen migration is stale."
    )


def test_upgrade_0007_full_old_shape_e2e(tmp_path):  # noqa: PLR0915
    """Full upgrade() of 0007 against a real OLD-shape (6.x) database.

    Exercises every DDL step in the real 6.x→7.0 upgrade path:
      - add description column
      - fold name:value → name + case-insensitive dedupe
      - backfill color + make NOT NULL
      - drop value column
      - add uq_tags_name unique constraint
      - add six composite-unique constraints via batch_alter_table

    The specific sharp edge under test: SQLite batch-mode rebuilds of tables
    with composite FKs (agent_task_tag_assc has a composite FK to agent_tasks).
    Alembic must carry the FK over during the rebuild — this asserts it does.

    SCOPE: this is SQLite-backed, so it covers the DDL-step ordering, the fold
    DML, and the batch-rebuild FK carry-over — but NOT the MySQL-only implicit-
    COMMIT-between-DDL-steps semantics the migration is written around (on SQLite
    DDL is transactional). The CONCAT-vs-`||` dialect hazard is covered separately
    by test_fold_name_sql_is_dialect_aware; the implicit-commit ordering is not
    exercised here.
    """
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, inspect, text

    mig = _load_0007_migration()

    # Build the old-shape schema in a fresh temp SQLite DB.
    engine = create_engine(f"sqlite:///{tmp_path}/old.db")
    with engine.begin() as conn:
        # Minimal stub tables so composite FK targets exist for reflection.
        conn.execute(text("CREATE TABLE listeners (id INTEGER PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE agents (session_id TEXT PRIMARY KEY)"))
        conn.execute(
            text(
                "CREATE TABLE agent_tasks "
                "(id INTEGER, agent_id TEXT, PRIMARY KEY(id, agent_id))"
            )
        )
        conn.execute(text("CREATE TABLE plugin_tasks (id INTEGER PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE credentials (id INTEGER PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE downloads (id INTEGER PRIMARY KEY)"))

        # Old-shape tags: has value, color nullable, NO unique on name, NO description.
        conn.execute(
            text(
                "CREATE TABLE tags "
                "(id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
                "value TEXT NOT NULL, color TEXT)"
            )
        )

        # Six association tables in old shape (no unique constraints yet).
        conn.execute(
            text(
                "CREATE TABLE listener_tag_assc "
                "(listener_id INTEGER, tag_id INTEGER, "
                "FOREIGN KEY (listener_id) REFERENCES listeners(id), "
                "FOREIGN KEY (tag_id) REFERENCES tags(id))"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE agent_tag_assc "
                "(agent_id TEXT, tag_id INTEGER, "
                "FOREIGN KEY (agent_id) REFERENCES agents(session_id), "
                "FOREIGN KEY (tag_id) REFERENCES tags(id))"
            )
        )
        # agent_task_tag_assc: composite FK — the SQLite batch-rebuild sharp edge.
        conn.execute(
            text(
                "CREATE TABLE agent_task_tag_assc "
                "(agent_task_id INTEGER, agent_id TEXT, tag_id INTEGER, "
                "FOREIGN KEY (agent_task_id, agent_id) "
                "REFERENCES agent_tasks(id, agent_id), "
                "FOREIGN KEY (tag_id) REFERENCES tags(id))"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE plugin_task_tag_assc "
                "(plugin_task_id INTEGER, tag_id INTEGER, "
                "FOREIGN KEY (plugin_task_id) REFERENCES plugin_tasks(id), "
                "FOREIGN KEY (tag_id) REFERENCES tags(id))"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE credential_tag_assc "
                "(credential_id INTEGER, tag_id INTEGER, "
                "FOREIGN KEY (credential_id) REFERENCES credentials(id), "
                "FOREIGN KEY (tag_id) REFERENCES tags(id))"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE download_tag_assc "
                "(download_id INTEGER, tag_id INTEGER, "
                "FOREIGN KEY (download_id) REFERENCES downloads(id), "
                "FOREIGN KEY (tag_id) REFERENCES tags(id))"
            )
        )

        # Seed old-shape tags: two rows that fold+dedupe to os:windows, plus task:input.
        conn.execute(
            text(
                "INSERT INTO tags (id, name, value, color) VALUES "
                "(1, 'os', 'windows', NULL), "
                "(2, 'os', 'windows', '#abc123'), "
                "(3, 'task', 'input', NULL)"
            )
        )
        # Seed agent_tasks and agent_task_tag_assc rows (exercises the composite FK path).
        conn.execute(text("INSERT INTO agent_tasks VALUES (1, 'abc123')"))
        conn.execute(text("INSERT INTO agent_task_tag_assc VALUES (1, 'abc123', 1)"))
        # Seed download_tag_assc (duplicate rows that should dedupe post-fold).
        conn.execute(
            text(
                "INSERT INTO download_tag_assc (download_id, tag_id) VALUES (10, 1), (10, 2)"
            )
        )

    # Run the FULL upgrade() using Alembic's Operations.context to install op proxy.
    with engine.begin() as conn:
        mc = MigrationContext.configure(conn)
        with Operations.context(mc):
            mig.upgrade()

    # ---------- assertions ----------
    with engine.connect() as conn:
        insp = inspect(conn)

        # 1. tags schema: no value, has description, color NOT NULL, uq_tags_name exists.
        tags_cols = {c["name"]: c for c in insp.get_columns("tags")}
        assert "value" not in tags_cols, "value column should have been dropped"
        assert "description" in tags_cols, "description column must be present"
        color_col = tags_cols["color"]
        assert not color_col["nullable"], "color must be NOT NULL after migration"

        all_uq = {u["name"] for u in insp.get_unique_constraints("tags")}
        all_idx = {i["name"] for i in insp.get_indexes("tags")}
        assert "uq_tags_name" in (all_uq | all_idx), "uq_tags_name must exist on tags"

        # 2. Composite-unique constraints on all six association tables.
        expected_uq = {
            "listener_tag_assc": "uq_listener_tag",
            "agent_tag_assc": "uq_agent_tag",
            "agent_task_tag_assc": "uq_agent_task_tag",
            "plugin_task_tag_assc": "uq_plugin_task_tag",
            "credential_tag_assc": "uq_credential_tag",
            "download_tag_assc": "uq_download_tag",
        }
        for tbl, uq_name in expected_uq.items():
            tbl_uq = {u["name"] for u in insp.get_unique_constraints(tbl)}
            tbl_idx = {i["name"] for i in insp.get_indexes(tbl)}
            assert uq_name in (tbl_uq | tbl_idx), (
                f"{tbl} is missing unique constraint {uq_name}"
            )

        # 3. The composite FK on agent_task_tag_assc survived the batch rebuild.
        fks = insp.get_foreign_keys("agent_task_tag_assc")
        composite_fk = next(
            (
                fk
                for fk in fks
                if fk["referred_table"] == "agent_tasks"
                and set(fk["constrained_columns"]) == {"agent_task_id", "agent_id"}
            ),
            None,
        )
        assert composite_fk is not None, (
            "Composite FK (agent_task_id, agent_id) → agent_tasks was LOST during "
            "the batch rebuild — Alembic dropped it. This is a bug in the migration."
        )
        assert set(composite_fk["referred_columns"]) == {"id", "agent_id"}, (
            "Composite FK referred columns must be (id, agent_id) on agent_tasks"
        )

        # 4. Data integrity: fold+dedupe produced two surviving tags.
        tag_rows = conn.execute(
            text("SELECT name, color FROM tags ORDER BY name")
        ).all()
        tag_names = [r[0] for r in tag_rows]
        assert tag_names == ["os:windows", "task:input"], (
            f"Unexpected tag names after fold+dedupe: {tag_names}"
        )
        # os:windows survivor should have been assigned the non-null color from id=2.
        os_color = next(r[1] for r in tag_rows if r[0] == "os:windows")
        assert os_color == "#abc123", f"Expected survivor color #abc123, got {os_color}"
        # task:input had no color — migration should have backfilled one.
        task_color = next(r[1] for r in tag_rows if r[0] == "task:input")
        assert task_color is not None, (
            f"task:input color must be backfilled, got {task_color!r}"
        )
        assert task_color.startswith("#"), (
            f"task:input color must be a hex string, got {task_color!r}"
        )

        # 5. Association rows survived and deduplicated.
        att_rows = conn.execute(text("SELECT * FROM agent_task_tag_assc")).all()
        assert len(att_rows) == 1, (
            f"agent_task_tag_assc should have 1 row, got {att_rows}"
        )
        surviving_tag_ids = {
            r[0] for r in conn.execute(text("SELECT id FROM tags")).all()
        }
        assert att_rows[0][2] in surviving_tag_ids, (
            "agent_task_tag_assc.tag_id must point to a surviving tag"
        )

        # download_tag_assc: two rows pointing to the same tag post-fold must dedupe to one.
        dt_rows = conn.execute(text("SELECT * FROM download_tag_assc")).all()
        assert len(dt_rows) == 1, (
            f"download_tag_assc should have deduplicated to 1 row, got {dt_rows}"
        )
        assert dt_rows[0][1] in surviving_tag_ids, (
            "download_tag_assc.tag_id must point to a surviving tag"
        )

    engine.dispose()


@pytest.mark.usefixtures("_restore_db_to_baseline_after")
def test_migration_0004_upgrade_downgrade_roundtrip(client):
    """0004.upgrade() is idempotent against existing indexes; downgrade() drops them; re-upgrade restores."""
    from alembic import command
    from sqlalchemy import inspect as sa_inspect

    from empire.server.core.db.base import _alembic_cfg, engine, use

    cfg = _alembic_cfg()

    try:
        # Ensure we start at head.
        command.stamp(cfg, "head")

        # 0004.upgrade() against a DB that already has the indexes (via
        # create_all on fresh installs) must no-op cleanly.
        command.downgrade(cfg, "0003")
        insp = sa_inspect(engine)

        # After downgrade, the three freely-droppable indexes should be gone.
        agent_indexes = {ix["name"] for ix in insp.get_indexes("agents")}
        user_indexes = {ix["name"] for ix in insp.get_indexes("users")}
        agent_file_indexes = {ix["name"] for ix in insp.get_indexes("agent_files")}
        assert "ix_agents_listener_archived" not in agent_indexes
        assert "ix_users_username" not in user_indexes
        assert "ix_agent_files_session_id" not in agent_file_indexes
        # ix_agent_files_parent_id backs the self-referential FK on
        # agent_files.parent_id. InnoDB requires an index on the FK column, so
        # downgrade() intentionally leaves it on MySQL; SQLite drops it.
        if use == "mysql":
            assert "ix_agent_files_parent_id" in agent_file_indexes
        else:
            assert "ix_agent_files_parent_id" not in agent_file_indexes

        # Upgrade again — should restore the indexes.
        command.upgrade(cfg, "head")
        insp = sa_inspect(engine)
        agent_indexes = {ix["name"] for ix in insp.get_indexes("agents")}
        user_indexes = {ix["name"] for ix in insp.get_indexes("users")}
        agent_file_indexes = {ix["name"] for ix in insp.get_indexes("agent_files")}
        assert "ix_agents_listener_archived" in agent_indexes
        assert "ix_users_username" in user_indexes
        assert "ix_agent_files_session_id" in agent_file_indexes
        assert "ix_agent_files_parent_id" in agent_file_indexes

        # Re-upgrade (idempotency check): must not error.
        command.upgrade(cfg, "head")
    finally:
        # Always leave the DB at head + alembic_version row at head so we
        # don't leak state into the rest of the suite, even if an assertion
        # above failed mid-roundtrip.
        command.upgrade(cfg, "head")
        command.stamp(cfg, "head")
