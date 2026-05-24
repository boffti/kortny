"""episodic task memory

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-24

Adds a bounded, non-vector task episode table. workspace_state stores
confirmed durable facts; episodes store compact provenance for work Kortny did.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "episodes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("installation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("thread_ts", sa.String(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "tools_used",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "artifacts_created",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "source_refs",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("error_json", postgresql.JSONB(), nullable=True),
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
        sa.CheckConstraint(
            "outcome in ('succeeded', 'failed', 'cancelled')",
            name="ck_episodes_outcome",
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"], ["installations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", name="idx_episodes_task_unique"),
    )
    op.create_index(
        "idx_episodes_thread",
        "episodes",
        ["installation_id", "channel_id", "thread_ts"],
    )
    op.create_index(
        "idx_episodes_channel",
        "episodes",
        ["installation_id", "channel_id", "created_at"],
    )
    op.create_index(
        "idx_episodes_user",
        "episodes",
        ["installation_id", "user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_episodes_user", table_name="episodes")
    op.drop_index("idx_episodes_channel", table_name="episodes")
    op.drop_index("idx_episodes_thread", table_name="episodes")
    op.drop_table("episodes")
