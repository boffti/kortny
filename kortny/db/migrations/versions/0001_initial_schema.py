"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-22

Creates the seven MVP tables, three native enum types, and all indexes,
matching the locked DBML schema.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# Enum types are created/dropped explicitly (create_type=False on the columns).
task_status = postgresql.ENUM(
    "pending",
    "running",
    "succeeded",
    "failed",
    "crashed",
    "cancelled",
    name="task_status",
    create_type=False,
)
llm_provider = postgresql.ENUM(
    "openai",
    "anthropic",
    "openrouter",
    name="llm_provider",
    create_type=False,
)
task_event_type = postgresql.ENUM(
    "task_created",
    "status_changed",
    "llm_call",
    "tool_call",
    "tool_result",
    "artifact_created",
    "message_posted",
    "error",
    "log",
    name="task_event_type",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    task_status.create(bind, checkfirst=True)
    llm_provider.create(bind, checkfirst=True)
    task_event_type.create(bind, checkfirst=True)

    op.create_table(
        "installations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("slack_team_id", sa.String(), nullable=False),
        sa.Column("team_name", sa.String(), nullable=True),
        sa.Column("bot_user_id", sa.String(), nullable=True),
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
        sa.UniqueConstraint("slack_team_id"),
    )

    op.create_table(
        "encrypted_secrets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("installation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("secret_type", sa.String(), nullable=False),
        sa.Column("ciphertext", postgresql.BYTEA(), nullable=False),
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
        sa.ForeignKeyConstraint(["installation_id"], ["installations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("installation_id", "secret_type", name="idx_secret_lookup"),
    )

    op.create_table(
        "tasks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("installation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("slack_event_id", sa.String(), nullable=True),
        sa.Column("slack_channel_id", sa.String(), nullable=False),
        sa.Column("slack_thread_ts", sa.String(), nullable=True),
        sa.Column("slack_message_ts", sa.String(), nullable=True),
        sa.Column("slack_user_id", sa.String(), nullable=False),
        sa.Column("input", sa.Text(), nullable=False),
        sa.Column(
            "status",
            task_status,
            server_default=sa.text("'pending'::task_status"),
            nullable=False,
        ),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("error", postgresql.JSONB(), nullable=True),
        sa.Column(
            "available_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("locked_by", sa.String(), nullable=True),
        sa.Column("locked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "attempts", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "max_attempts", sa.Integer(), server_default=sa.text("3"), nullable=False
        ),
        sa.Column(
            "total_input_tokens",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "total_output_tokens",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "total_cost_usd",
            sa.Numeric(12, 6),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["installation_id"], ["installations.id"]),
        sa.ForeignKeyConstraint(["parent_task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slack_event_id"),
    )
    op.create_index("idx_tasks_claim", "tasks", ["status", "available_at"])
    op.create_index("idx_tasks_history", "tasks", ["installation_id", "created_at"])
    op.create_index(
        "idx_tasks_thread", "tasks", ["slack_channel_id", "slack_thread_ts"]
    )

    op.create_table(
        "task_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("type", task_event_type, nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "seq", name="idx_events_task_seq"),
    )

    op.create_table(
        "llm_usage",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=True),
        sa.Column("provider", llm_provider, nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column(
            "input_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "output_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "cost_usd", sa.Numeric(12, 6), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.ForeignKeyConstraint(["event_id"], ["task_events.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_usage_task", "llm_usage", ["task_id"])
    op.create_index("idx_usage_time", "llm_usage", ["created_at"])

    op.create_table(
        "artifacts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("mime_type", sa.String(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("storage_path", sa.String(), nullable=True),
        sa.Column("slack_file_id", sa.String(), nullable=True),
        sa.Column("posted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_artifacts_task", "artifacts", ["task_id"])

    op.create_table(
        "model_pricing",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("provider", llm_provider, nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("input_price_per_mtok", sa.Numeric(12, 6), nullable=False),
        sa.Column("output_price_per_mtok", sa.Numeric(12, 6), nullable=False),
        sa.Column(
            "effective_from",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "model", "effective_from", name="idx_pricing_lookup"
        ),
    )


def downgrade() -> None:
    op.drop_table("model_pricing")
    op.drop_index("idx_artifacts_task", table_name="artifacts")
    op.drop_table("artifacts")
    op.drop_index("idx_usage_time", table_name="llm_usage")
    op.drop_index("idx_usage_task", table_name="llm_usage")
    op.drop_table("llm_usage")
    op.drop_table("task_events")
    op.drop_index("idx_tasks_thread", table_name="tasks")
    op.drop_index("idx_tasks_history", table_name="tasks")
    op.drop_index("idx_tasks_claim", table_name="tasks")
    op.drop_table("tasks")
    op.drop_table("encrypted_secrets")
    op.drop_table("installations")

    bind = op.get_bind()
    task_event_type.drop(bind, checkfirst=True)
    llm_provider.drop(bind, checkfirst=True)
    task_status.drop(bind, checkfirst=True)
