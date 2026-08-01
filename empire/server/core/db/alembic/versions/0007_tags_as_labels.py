"""rework tags into a shared GitHub-style label registry

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-23

Folds the old per-entity ``tags(name, value)`` rows into a shared registry where
``name`` is unique and carries a single ``color`` + ``description``. The fold is
ROW-LEVEL IDEMPOTENT: it rewrites ``name`` and clears ``value`` to '' in one pass
and only touches rows where ``value <> ''``. On MySQL, DDL implicitly commits, so
a failure between the fold and the ``value`` drop must not double-fold on re-run.

Idempotent/schema-aware: this runs against the already-final ``create_all`` schema
on fresh installs (stamped to 0001 then upgraded to head), so every step guards on
the live schema and no-ops when already applied. Uses raw SQL / reflected Tables —
never the ORM ``Tag`` (which no longer has ``value``).

LIMITATION: the dedupe groups names by Python ``str.lower()``, which is not always
equivalent to the DB's unique-name collation. On a MySQL server whose default
collation is accent-insensitive (e.g. utf8mb4_0900_ai_ci) two folded names that
differ only by accent/special-casing (``cafe`` vs ``café``) survive the Python
dedupe but collide when ``uq_tags_name`` is added, failing the upgrade. ASCII tag
names — the overwhelmingly common case — are unaffected. If this bites a real
upgrade, hand-dedupe the offending ``tags`` rows and re-run.

The same blanket ``str.lower()`` cuts the other way on SQLite: post-migration,
``tags.name`` uniqueness is case-SENSITIVE on SQLite (default BINARY collation)
but case-INSENSITIVE on MySQL (table collation) — see tag_service.get_or_create_tag.
So on a SQLite install, two pre-migration tags differing only by case (e.g. old
``Prod:x`` and ``prod:x`` rows, valid before this migration since the old model
had no unique constraint) get merged by this fold into one registry tag, even
though the post-migration SQLite model would otherwise keep them distinct. Benign
(associations are rewired to the surviving tag, nothing orphaned/crashes) and
narrow (only matters for existing SQLite installs with such case-variant tags),
so left as a documented limitation rather than a dialect-aware behavior change.
"""

import hashlib
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ASSC_TABLES = (
    "listener_tag_assc",
    "agent_tag_assc",
    "agent_task_tag_assc",
    "plugin_task_tag_assc",
    "credential_tag_assc",
    "download_tag_assc",
)


def _color_from_name(name: str) -> str:
    """Frozen copy of tag_service.color_from_name (migrations must be stable)."""
    digest = hashlib.md5(name.encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"#{digest[:6]}"


def _has_column(insp, table: str, column: str) -> bool:
    return any(c["name"] == column for c in insp.get_columns(table))


def _fold_name_sql(dialect_name: str) -> str:
    """SQL expression folding ``name`` + ``value`` into ``name:value`` per dialect.

    MySQL's ``||`` is the logical-OR operator (not string concat) unless
    ``PIPES_AS_CONCAT`` SQL mode is set — which is NOT the default — so on MySQL
    ``name || ':' || value`` would evaluate to a number and destroy every name.
    MySQL must use ``CONCAT(...)``; SQLite uses ``||``.
    """
    if dialect_name == "mysql":
        return "CONCAT(name, ':', value)"
    return "name || ':' || value"


def _fold_tags(bind) -> None:
    """Row-level idempotent fold + case-insensitive dedupe + association rewire.

    Safe to call repeatedly via two guards: it returns immediately when the
    ``value`` column is absent (fresh install or already-migrated DB), and when
    present it only rewrites un-folded rows (``value <> ''``), clearing ``value``
    to '' as it goes — so a re-run after a partial failure cannot double-fold.
    """
    insp = inspect(bind)
    if "tags" not in insp.get_table_names() or not _has_column(insp, "tags", "value"):
        return  # already final-shape — nothing to fold

    # 1. Rewrite name and clear value in one pass; only un-folded rows (value<>'').
    #    Dialect-aware concat: MySQL `||` is OR, not string concatenation.
    fold_expr = _fold_name_sql(bind.dialect.name)
    bind.execute(
        text(f"UPDATE tags SET name = {fold_expr}, value = '' WHERE value <> ''")  # noqa: S608
    )

    # 2. Dedupe survivors by case-folded name, recomputed from current state.
    rows = bind.execute(text("SELECT id, name, color FROM tags")).all()
    groups: dict[str, list] = {}
    for tid, name, color in rows:
        groups.setdefault(name.lower(), []).append((tid, name, color))

    present_assc = [t for t in _ASSC_TABLES if t in insp.get_table_names()]
    for members in groups.values():
        members.sort(key=lambda m: m[0])
        survivor_id, survivor_name, _ = members[0]
        colors = [c for _, _, c in members if c]
        survivor_color = colors[0] if colors else _color_from_name(survivor_name)
        bind.execute(
            text("UPDATE tags SET color = :c WHERE id = :i"),
            {"c": survivor_color, "i": survivor_id},
        )
        dup_ids = [m[0] for m in members[1:]]
        for dup_id in dup_ids:
            for tbl in present_assc:
                bind.execute(
                    text(f"UPDATE {tbl} SET tag_id = :s WHERE tag_id = :d"),  # noqa: S608
                    {"s": survivor_id, "d": dup_id},
                )
            bind.execute(text("DELETE FROM tags WHERE id = :i"), {"i": dup_id})

    # 3. Dedupe association rows that now point at the same (entity..., tag) tuple.
    _dedupe_associations(bind, present_assc)


def _dedupe_associations(bind, present_assc) -> None:
    """Remove duplicate association rows (created when the case-fold merges two
    labels that were both attached to the same entity). Association tables hold
    ONLY their key columns, so identical tuples are exact duplicates.

    Non-destructive in the common case: a table with no duplicates is left
    completely untouched (no DELETE runs). When duplicates do exist, the table is
    rebuilt from its distinct rows via a DELETE + INSERT. The two statements run
    consecutively with NO DDL between them, so they share one transaction and a
    failed INSERT rolls back the DELETE rather than leaving the table empty.
    (A temp-table rebuild was avoided: its ``DROP`` implicitly commits on MySQL —
    which would strand the DELETE in its own committed transaction — and the
    ``DROP TEMPORARY TABLE`` form SQLite rejects.)
    """
    insp = inspect(bind)
    for tbl in present_assc:
        cols = [c["name"] for c in insp.get_columns(tbl)]
        col_list = ", ".join(cols)
        rows = bind.execute(text(f"SELECT {col_list} FROM {tbl}")).all()  # noqa: S608
        distinct = list(dict.fromkeys(tuple(r) for r in rows))
        if len(distinct) == len(rows):
            continue  # no duplicates — leave the table untouched
        placeholders = ", ".join(f":{c}" for c in cols)
        bind.execute(text(f"DELETE FROM {tbl}"))  # noqa: S608
        bind.execute(
            text(f"INSERT INTO {tbl} ({col_list}) VALUES ({placeholders})"),  # noqa: S608
            [dict(zip(cols, vals, strict=True)) for vals in distinct],
        )


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if "tags" not in insp.get_table_names():
        raise RuntimeError(
            "Migration 0007 expected table 'tags' to exist. DB schema is partial "
            "— restore from backup or run 'server --clean' to reset."
        )

    # 1. fold + dedupe FIRST, before any DDL. _fold_tags reads and writes the
    #    `value` column that step 4 drops (so it must precede that DDL), and it
    #    must collapse duplicate names before steps 5-6 add the unique constraints
    #    that would otherwise reject them. Doing all the DML here also keeps it in
    #    one transaction on MySQL, where each batch_alter_table below issues an
    #    implicit COMMIT that would strand preceding DML in its own committed
    #    transaction. No-op on the already-final schema (value column absent).
    _fold_tags(bind)

    # 2. description column.
    insp = inspect(bind)
    if not _has_column(insp, "tags", "description"):
        with op.batch_alter_table("tags") as batch:
            batch.add_column(sa.Column("description", sa.Text(), nullable=True))

    # 3. color NOT NULL (backfill nulls deterministically first).
    insp = inspect(bind)
    color_col = next(c for c in insp.get_columns("tags") if c["name"] == "color")
    if color_col["nullable"]:
        for tid, name in bind.execute(
            text("SELECT id, name FROM tags WHERE color IS NULL")
        ).all():
            bind.execute(
                text("UPDATE tags SET color = :c WHERE id = :i"),
                {"c": _color_from_name(name), "i": tid},
            )
        with op.batch_alter_table("tags") as batch:
            batch.alter_column("color", existing_type=sa.String(12), nullable=False)

    # 4. drop value.
    insp = inspect(bind)
    if _has_column(insp, "tags", "value"):
        with op.batch_alter_table("tags") as batch:
            batch.drop_column("value")

    # 5. unique(name).
    insp = inspect(bind)
    uniques = {u["name"] for u in insp.get_unique_constraints("tags")}
    idx_names = {i["name"] for i in insp.get_indexes("tags")}
    if "uq_tags_name" not in uniques and "uq_tags_name" not in idx_names:
        with op.batch_alter_table("tags") as batch:
            batch.create_unique_constraint("uq_tags_name", ["name"])

    # 6. composite-unique per association table.
    insp = inspect(bind)
    key_cols = {
        "listener_tag_assc": ("listener_id", "tag_id"),
        "agent_tag_assc": ("agent_id", "tag_id"),
        "agent_task_tag_assc": ("agent_task_id", "agent_id", "tag_id"),
        "plugin_task_tag_assc": ("plugin_task_id", "tag_id"),
        "credential_tag_assc": ("credential_id", "tag_id"),
        "download_tag_assc": ("download_id", "tag_id"),
    }
    for tbl, cols in key_cols.items():
        if tbl not in insp.get_table_names():
            continue
        name = f"uq_{tbl[: -len('_tag_assc')]}_tag"
        existing = {u["name"] for u in insp.get_unique_constraints(tbl)}
        existing |= {i["name"] for i in insp.get_indexes(tbl)}
        if name not in existing:
            with op.batch_alter_table(tbl) as batch:
                batch.create_unique_constraint(name, list(cols))


def downgrade() -> None:
    # No-op / best-effort: a folded name cannot be losslessly split back into
    # name/value, consistent with the baseline migration's approach.
    pass
