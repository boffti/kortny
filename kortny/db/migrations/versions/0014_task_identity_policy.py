"""task identity policy

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-28

Adds a first-class idempotency identity to tasks. New tasks get a deterministic
identity key per installation; existing rows remain nullable for migration
safety and historical compatibility.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("identity_kind", sa.String(), nullable=True))
    op.add_column("tasks", sa.Column("identity_key", sa.String(), nullable=True))
    op.add_column(
        "tasks",
        sa.Column(
            "identity_payload",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "tasks", sa.Column("identity_fingerprint", sa.String(), nullable=True)
    )
    op.create_check_constraint(
        "ck_tasks_identity_kind",
        "tasks",
        "identity_kind is null or identity_kind in "
        "('slack_message', 'slack_event', 'synthetic', 'scheduled', 'manual')",
    )
    op.create_index(
        "idx_tasks_identity_unique",
        "tasks",
        ["installation_id", "identity_key"],
        unique=True,
        postgresql_where=sa.text("identity_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_tasks_identity_unique", table_name="tasks")
    op.drop_constraint("ck_tasks_identity_kind", "tasks", type_="check")
    op.drop_column("tasks", "identity_fingerprint")
    op.drop_column("tasks", "identity_payload")
    op.drop_column("tasks", "identity_key")
    op.drop_column("tasks", "identity_kind")
