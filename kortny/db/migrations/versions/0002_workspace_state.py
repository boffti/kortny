"""workspace state memory table

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-23

Adds the L1 structured memory table for confirmation-gated workspace facts.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_state",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("installation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope_type", sa.String(), nullable=False),
        sa.Column("scope_id", sa.String(), nullable=True),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value_json", postgresql.JSONB(), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("source_kind", sa.String(), nullable=False),
        sa.Column("source_task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_event_id", sa.BigInteger(), nullable=True),
        sa.Column("source_slack_channel_id", sa.String(), nullable=True),
        sa.Column("source_slack_message_ts", sa.String(), nullable=True),
        sa.Column("source_slack_file_id", sa.String(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("proposed_by", sa.String(), nullable=False),
        sa.Column("proposed_reason", sa.Text(), nullable=True),
        sa.Column("confidence_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("confidence_reason", sa.Text(), nullable=True),
        sa.Column("confirmed_by_user_id", sa.String(), nullable=True),
        sa.Column("confirmed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("rejected_by_user_id", sa.String(), nullable=True),
        sa.Column("rejected_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("superseded_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("superseded_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("forgotten_by_user_id", sa.String(), nullable=True),
        sa.Column("forgotten_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
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
            name="ck_workspace_state_scope_type",
        ),
        sa.CheckConstraint(
            "status in ('proposed', 'active', 'rejected', 'superseded', 'forgotten')",
            name="ck_workspace_state_status",
        ),
        sa.CheckConstraint(
            "source_kind in "
            "('user_explicit', 'agent_proposed', 'summarizer_proposed', "
            "'observer_proposed', 'import')",
            name="ck_workspace_state_source_kind",
        ),
        sa.CheckConstraint(
            "(scope_type = 'workspace' and scope_id is null) or "
            "(scope_type in ('channel', 'user') and scope_id is not null)",
            name="ck_workspace_state_scope_id",
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"], ["installations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["source_task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["source_event_id"], ["task_events.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["superseded_by_id"], ["workspace_state.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_workspace_state_active_unique",
        "workspace_state",
        [
            "installation_id",
            "scope_type",
            sa.text("coalesce(scope_id, '')"),
            "key",
        ],
        unique=True,
        postgresql_where=sa.text("status = 'active' AND expires_at IS NULL"),
    )
    op.create_index(
        "idx_workspace_state_active_lookup",
        "workspace_state",
        ["installation_id", "status", "scope_type", "scope_id"],
    )
    op.create_index(
        "idx_workspace_state_source",
        "workspace_state",
        ["source_task_id", "source_event_id"],
    )
    op.create_index(
        "idx_workspace_state_expires_at",
        "workspace_state",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_workspace_state_expires_at", table_name="workspace_state")
    op.drop_index("idx_workspace_state_source", table_name="workspace_state")
    op.drop_index("idx_workspace_state_active_lookup", table_name="workspace_state")
    op.drop_index("idx_workspace_state_active_unique", table_name="workspace_state")
    op.drop_table("workspace_state")
