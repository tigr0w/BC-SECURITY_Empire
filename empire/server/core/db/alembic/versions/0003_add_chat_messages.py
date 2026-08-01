"""add chat_messages table

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from empire.server.core.db.utc_datetime import UtcDateTime, utcnow

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "chat_messages" not in inspector.get_table_names():
        op.create_table(
            "chat_messages",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
            sa.Column("username", sa.String(255), nullable=False),
            sa.Column("message", sa.Text, nullable=False),
            sa.Column(
                "created_at",
                UtcDateTime(),
                server_default=utcnow(),
                nullable=False,
            ),
        )
        op.create_index(
            "ix_chat_messages_created_at",
            "chat_messages",
            ["created_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "chat_messages" in inspector.get_table_names():
        op.drop_index("ix_chat_messages_created_at", table_name="chat_messages")
        op.drop_table("chat_messages")
