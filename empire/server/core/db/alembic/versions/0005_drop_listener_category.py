"""drop listeners.listener_category

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-18

The listener_category column was only ever written (from the listener
template's category metadata) and never read or exposed, so the template
category was removed. Drop the now-dead column. Idempotent: skips the drop
if the column is already gone (e.g. fresh installs built from current
Base.metadata).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "listeners"
_COLUMN = "listener_category"


def _has_column(bind, table: str, column: str) -> bool:
    insp = inspect(bind)
    if table not in insp.get_table_names():
        raise RuntimeError(
            f"Migration 0005 expected table '{table}' to exist (it should "
            f"have been created via Base.metadata or an earlier migration). "
            f"DB schema is partial — restore from backup or run "
            f"'server --clean' to reset."
        )
    return any(col["name"] == column for col in insp.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, _TABLE, _COLUMN):
        with op.batch_alter_table(_TABLE) as batch_op:
            batch_op.drop_column(_COLUMN)


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, _TABLE, _COLUMN):
        # Re-add with a server default so the NOT NULL column backfills
        # cleanly on tables that already hold rows.
        with op.batch_alter_table(_TABLE) as batch_op:
            batch_op.add_column(
                sa.Column(
                    _COLUMN,
                    sa.String(255),
                    nullable=False,
                    server_default="",
                )
            )
