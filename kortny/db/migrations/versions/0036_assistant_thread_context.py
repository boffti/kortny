"""Assistant thread context store (HIG-236).

Revision ID: 0036
Revises: 0035
Create Date: 2026-06-11

Backs HIG-236 (assistant thread surface). Slack assistant-thread ``message.im``
events do not carry the channel the user was viewing when they opened the
assistant, so the app persists that context here. One row per
(channel_id, thread_ts); the Postgres-backed implementation of slack_bolt's
``AssistantThreadContextStore`` upserts into this table.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_thread_context",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("channel_id", sa.String(), nullable=False),
        sa.Column("thread_ts", sa.String(), nullable=False),
        sa.Column(
            "context_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "channel_id",
            "thread_ts",
            name="uq_assistant_thread_context_channel_thread",
        ),
    )


def downgrade() -> None:
    op.drop_table("assistant_thread_context")
