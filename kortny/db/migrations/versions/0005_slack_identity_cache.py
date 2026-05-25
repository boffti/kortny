"""slack identity cache

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-25

Adds a small Slack user/channel identity cache for dashboard display names.
Dashboard reads stay database-only; Slack API refreshes happen from ingress.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "slack_identities",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("installation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("slack_id", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("raw_name", sa.String(), nullable=True),
        sa.Column(
            "is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "is_bot", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "is_private", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "raw_json",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("refreshed_at", sa.TIMESTAMP(timezone=True), nullable=True),
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
            "kind in ('user', 'channel')", name="ck_slack_identity_kind"
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"], ["installations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "installation_id",
            "kind",
            "slack_id",
            name="idx_slack_identity_unique",
        ),
    )
    op.create_index(
        "idx_slack_identity_lookup",
        "slack_identities",
        ["installation_id", "kind", "slack_id"],
    )
    op.create_index(
        "idx_slack_identity_seen",
        "slack_identities",
        ["installation_id", "kind", "last_seen_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_slack_identity_seen", table_name="slack_identities")
    op.drop_index("idx_slack_identity_lookup", table_name="slack_identities")
    op.drop_table("slack_identities")
