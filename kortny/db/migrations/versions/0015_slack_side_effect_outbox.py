"""slack side effect outbox

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-31

Stores Slack API side effects with deterministic idempotency keys so visible
Slack behavior can be retried or deduped independently from task execution.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "slack_side_effects",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("installation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("operation", sa.String(), nullable=False),
        sa.Column("purpose", sa.String(), nullable=True),
        sa.Column("target_channel_id", sa.String(), nullable=True),
        sa.Column("target_thread_ts", sa.String(), nullable=True),
        sa.Column("target_message_ts", sa.String(), nullable=True),
        sa.Column(
            "request_json",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("response_json", postgresql.JSONB(), nullable=True),
        sa.Column(
            "status", sa.String(), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column(
            "attempts", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("last_error", postgresql.JSONB(), nullable=True),
        sa.Column(
            "available_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.TIMESTAMP(timezone=True), nullable=True),
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
            "operation in "
            "('chat_postMessage', 'files_upload_v2', 'reactions_add', "
            "'reactions_remove')",
            name="ck_slack_side_effects_operation",
        ),
        sa.CheckConstraint(
            "status in ('pending', 'in_progress', 'succeeded', 'failed')",
            name="ck_slack_side_effects_status",
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"],
            ["installations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "installation_id",
            "idempotency_key",
            name="idx_slack_side_effects_idempotency",
        ),
    )
    op.create_index(
        "idx_slack_side_effects_status",
        "slack_side_effects",
        ["installation_id", "status", "available_at"],
    )
    op.create_index(
        "idx_slack_side_effects_task",
        "slack_side_effects",
        ["task_id", "created_at"],
    )
    op.create_index(
        "idx_slack_side_effects_target",
        "slack_side_effects",
        ["installation_id", "target_channel_id", "target_message_ts"],
    )


def downgrade() -> None:
    op.drop_index("idx_slack_side_effects_target", table_name="slack_side_effects")
    op.drop_index("idx_slack_side_effects_task", table_name="slack_side_effects")
    op.drop_index("idx_slack_side_effects_status", table_name="slack_side_effects")
    op.drop_table("slack_side_effects")
