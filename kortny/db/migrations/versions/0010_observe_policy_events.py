"""observe policies and events

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-27

Adds the Postgres-first substrate for Kortny Observe. This records bounded,
policy-gated Slack observations without creating inferred memories yet.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "observe_policies",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("installation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope_type", sa.String(), nullable=False),
        sa.Column("scope_id", sa.String(), nullable=True),
        sa.Column("observation_status", sa.String(), nullable=False),
        sa.Column("proactivity_status", sa.String(), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column(
            "quiet_hours_json",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("cooldown_seconds", sa.Integer(), nullable=True),
        sa.Column("enabled_by_user_id", sa.String(), nullable=True),
        sa.Column("enabled_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("paused_by_user_id", sa.String(), nullable=True),
        sa.Column("paused_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("pause_reason", sa.Text(), nullable=True),
        sa.Column(
            "metadata_json",
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
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "scope_type in ('workspace', 'channel', 'user')",
            name="ck_observe_policies_scope_type",
        ),
        sa.CheckConstraint(
            "observation_status in ('off', 'passive', 'active')",
            name="ck_observe_policies_observation_status",
        ),
        sa.CheckConstraint(
            "proactivity_status in ('off', 'digest_only', 'full')",
            name="ck_observe_policies_proactivity_status",
        ),
        sa.CheckConstraint(
            "(scope_type = 'workspace' and scope_id is null) or "
            "(scope_type in ('channel', 'user') and scope_id is not null)",
            name="ck_observe_policies_scope_id",
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"], ["installations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_observe_policies_scope_unique",
        "observe_policies",
        ["installation_id", "scope_type", sa.text("coalesce(scope_id, '')")],
        unique=True,
    )
    op.create_index(
        "idx_observe_policies_lookup",
        "observe_policies",
        ["installation_id", "scope_type", "scope_id", "observation_status"],
    )

    op.create_table(
        "observation_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("installation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slack_team_id", sa.String(), nullable=False),
        sa.Column("channel_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("slack_event_id", sa.String(), nullable=True),
        sa.Column("message_ts", sa.String(), nullable=True),
        sa.Column("thread_ts", sa.String(), nullable=True),
        sa.Column("file_id", sa.String(), nullable=True),
        sa.Column("raw_payload_checksum", sa.String(), nullable=False),
        sa.Column("text_preview", sa.Text(), nullable=True),
        sa.Column(
            "visibility_metadata",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "observed_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("purged_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_type in ('message', 'file_share', 'channel_join', 'channel_onboarding_intro')",
            name="ck_observation_events_event_type",
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"], ["installations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_observation_events_event_unique",
        "observation_events",
        ["installation_id", "slack_event_id"],
        unique=True,
        postgresql_where=sa.text("slack_event_id IS NOT NULL"),
    )
    op.create_index(
        "idx_observation_events_channel",
        "observation_events",
        ["installation_id", "channel_id", "observed_at"],
    )
    op.create_index(
        "idx_observation_events_user",
        "observation_events",
        ["installation_id", "user_id", "observed_at"],
    )
    op.create_index(
        "idx_observation_events_purged",
        "observation_events",
        ["purged_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_observation_events_purged", table_name="observation_events")
    op.drop_index("idx_observation_events_user", table_name="observation_events")
    op.drop_index("idx_observation_events_channel", table_name="observation_events")
    op.drop_index(
        "idx_observation_events_event_unique", table_name="observation_events"
    )
    op.drop_table("observation_events")

    op.drop_index("idx_observe_policies_lookup", table_name="observe_policies")
    op.drop_index("idx_observe_policies_scope_unique", table_name="observe_policies")
    op.drop_table("observe_policies")
