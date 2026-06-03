"""dashboard identity

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-26

Adds Slack-backed dashboard identity tables. The existing environment login
remains a bootstrap fallback; these tables are the durable user model for
personal dashboards, Composio connections, and future RBAC.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dashboard_users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("installation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slack_user_id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("avatar_url", sa.String(), nullable=True),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("last_login_at", sa.TIMESTAMP(timezone=True), nullable=True),
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
            "role in ('owner', 'admin', 'member')",
            name="ck_dashboard_users_role",
        ),
        sa.CheckConstraint(
            "status in ('active', 'disabled')",
            name="ck_dashboard_users_status",
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"], ["installations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "installation_id",
            "slack_user_id",
            name="idx_dashboard_users_slack_user_unique",
        ),
    )
    op.create_index(
        "idx_dashboard_users_installation_role",
        "dashboard_users",
        ["installation_id", "role"],
    )
    op.create_index(
        "idx_dashboard_users_status",
        "dashboard_users",
        ["installation_id", "status"],
    )
    op.create_index(
        "idx_dashboard_users_email_unique",
        "dashboard_users",
        ["installation_id", "email"],
        unique=True,
        postgresql_where=sa.text("email IS NOT NULL"),
    )

    op.create_table(
        "dashboard_oauth_states",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("redirect_path", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            "provider in ('slack')",
            name="ck_dashboard_oauth_states_provider",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state"),
    )
    op.create_index(
        "idx_dashboard_oauth_states_lookup",
        "dashboard_oauth_states",
        ["provider", "state", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_dashboard_oauth_states_lookup", table_name="dashboard_oauth_states"
    )
    op.drop_table("dashboard_oauth_states")
    op.drop_index("idx_dashboard_users_email_unique", table_name="dashboard_users")
    op.drop_index("idx_dashboard_users_status", table_name="dashboard_users")
    op.drop_index("idx_dashboard_users_installation_role", table_name="dashboard_users")
    op.drop_table("dashboard_users")
