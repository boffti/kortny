"""slack channel memberships

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-27

Tracks the Slack channels where Kortny is present separately from observe
policy. This keeps channel onboarding idempotent while leaving policy free to
answer what Kortny may observe or say.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "slack_channel_memberships",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("installation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_id", sa.String(), nullable=False),
        sa.Column("channel_name", sa.String(), nullable=True),
        sa.Column("channel_type", sa.String(), nullable=True),
        sa.Column(
            "membership_status",
            sa.String(),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column("discovered_via", sa.String(), nullable=False),
        sa.Column("added_by_user_id", sa.String(), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "onboarding_status",
            sa.String(),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("onboarding_posted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("onboarding_message_ts", sa.String(), nullable=True),
        sa.Column("last_event_id", sa.String(), nullable=True),
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
            "membership_status in ('active', 'left', 'unknown')",
            name="ck_slack_channel_memberships_status",
        ),
        sa.CheckConstraint(
            "discovered_via in "
            "('member_joined_channel', 'app_mention', 'message_observation', "
            "'channel_history', 'manual_backfill')",
            name="ck_slack_channel_memberships_discovered_via",
        ),
        sa.CheckConstraint(
            "onboarding_status in ('pending', 'posted', 'skipped')",
            name="ck_slack_channel_memberships_onboarding_status",
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"], ["installations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "installation_id",
            "channel_id",
            name="idx_slack_channel_memberships_unique",
        ),
    )
    op.create_index(
        "idx_slack_channel_memberships_lookup",
        "slack_channel_memberships",
        ["installation_id", "channel_id"],
    )
    op.create_index(
        "idx_slack_channel_memberships_status",
        "slack_channel_memberships",
        ["installation_id", "membership_status", "last_seen_at"],
    )
    op.create_index(
        "idx_slack_channel_memberships_onboarding",
        "slack_channel_memberships",
        ["installation_id", "onboarding_status", "last_seen_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_slack_channel_memberships_onboarding",
        table_name="slack_channel_memberships",
    )
    op.drop_index(
        "idx_slack_channel_memberships_status",
        table_name="slack_channel_memberships",
    )
    op.drop_index(
        "idx_slack_channel_memberships_lookup",
        table_name="slack_channel_memberships",
    )
    op.drop_table("slack_channel_memberships")
