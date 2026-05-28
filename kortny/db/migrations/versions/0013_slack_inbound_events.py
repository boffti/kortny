"""slack inbound event ledger

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-28

Stores every eligible Slack delivery before downstream task, observe, or
reaction side effects so retries and replays have a durable boundary.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "slack_inbound_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("installation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slack_team_id", sa.String(), nullable=False),
        sa.Column("slack_event_id", sa.String(), nullable=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("event_subtype", sa.String(), nullable=True),
        sa.Column("surface", sa.String(), nullable=False),
        sa.Column("channel_id", sa.String(), nullable=True),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("message_ts", sa.String(), nullable=True),
        sa.Column("thread_ts", sa.String(), nullable=True),
        sa.Column("event_time", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("retry_num", sa.Integer(), nullable=True),
        sa.Column("retry_reason", sa.String(), nullable=True),
        sa.Column(
            "raw_body",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "raw_event",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "processing_status",
            sa.String(),
            server_default=sa.text("'received'"),
            nullable=False,
        ),
        sa.Column(
            "processing_attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("observation_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("last_error", postgresql.JSONB(), nullable=True),
        sa.Column(
            "received_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("processed_at", sa.TIMESTAMP(timezone=True), nullable=True),
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
            "processing_status in "
            "('received', 'ignored', 'task_created', 'observed', "
            "'failed', 'dead_lettered', 'replayed')",
            name="ck_slack_inbound_events_processing_status",
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"], ["installations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["observation_event_id"], ["observation_events.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_slack_inbound_events_event_unique",
        "slack_inbound_events",
        ["installation_id", "slack_event_id"],
        unique=True,
        postgresql_where=sa.text("slack_event_id IS NOT NULL"),
    )
    op.create_index(
        "idx_slack_inbound_events_status",
        "slack_inbound_events",
        ["installation_id", "processing_status", "received_at"],
    )
    op.create_index(
        "idx_slack_inbound_events_channel",
        "slack_inbound_events",
        ["installation_id", "channel_id", "received_at"],
    )
    op.create_index(
        "idx_slack_inbound_events_task",
        "slack_inbound_events",
        ["task_id"],
    )
    op.create_index(
        "idx_slack_inbound_events_observation",
        "slack_inbound_events",
        ["observation_event_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_slack_inbound_events_observation",
        table_name="slack_inbound_events",
    )
    op.drop_index("idx_slack_inbound_events_task", table_name="slack_inbound_events")
    op.drop_index("idx_slack_inbound_events_channel", table_name="slack_inbound_events")
    op.drop_index("idx_slack_inbound_events_status", table_name="slack_inbound_events")
    op.drop_index(
        "idx_slack_inbound_events_event_unique",
        table_name="slack_inbound_events",
    )
    op.drop_table("slack_inbound_events")
