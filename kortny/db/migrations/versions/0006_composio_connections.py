"""composio scoped connections

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-26

Stores Composio connected-account metadata and Kortny visibility policy.
OAuth tokens stay in Composio; this table only gates which Slack task contexts
may use each external account.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "composio_connections",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("installation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("toolkit_slug", sa.String(), nullable=False),
        sa.Column("auth_config_id", sa.String(), nullable=True),
        sa.Column("connected_account_id", sa.String(), nullable=True),
        sa.Column("connection_request_id", sa.String(), nullable=True),
        sa.Column("composio_user_id", sa.String(), nullable=False),
        sa.Column("owner_slack_user_id", sa.String(), nullable=False),
        sa.Column("visibility_scope_type", sa.String(), nullable=False),
        sa.Column("visibility_scope_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("external_account_label", sa.String(), nullable=True),
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
            "visibility_scope_type in ('workspace', 'channel', 'user')",
            name="ck_composio_connections_visibility_scope_type",
        ),
        sa.CheckConstraint(
            "status in ('pending', 'active', 'expired', 'failed', 'disabled')",
            name="ck_composio_connections_status",
        ),
        sa.CheckConstraint(
            "(visibility_scope_type = 'workspace' and visibility_scope_id is null) or "
            "(visibility_scope_type in ('channel', 'user') and visibility_scope_id is not null)",
            name="ck_composio_connections_visibility_scope_id",
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"], ["installations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_composio_connections_connected_account",
        "composio_connections",
        ["installation_id", "connected_account_id"],
        unique=True,
        postgresql_where=sa.text("connected_account_id IS NOT NULL"),
    )
    op.create_index(
        "idx_composio_connections_allowed_lookup",
        "composio_connections",
        [
            "installation_id",
            "status",
            "visibility_scope_type",
            "visibility_scope_id",
        ],
    )
    op.create_index(
        "idx_composio_connections_owner",
        "composio_connections",
        ["installation_id", "owner_slack_user_id"],
    )
    op.create_index(
        "idx_composio_connections_toolkit",
        "composio_connections",
        ["installation_id", "toolkit_slug", "status"],
    )


def downgrade() -> None:
    op.drop_index("idx_composio_connections_toolkit", table_name="composio_connections")
    op.drop_index("idx_composio_connections_owner", table_name="composio_connections")
    op.drop_index(
        "idx_composio_connections_allowed_lookup", table_name="composio_connections"
    )
    op.drop_index(
        "idx_composio_connections_connected_account",
        table_name="composio_connections",
    )
    op.drop_table("composio_connections")
