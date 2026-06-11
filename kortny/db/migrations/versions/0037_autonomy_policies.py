"""autonomy policies (HIG-223)

Revision ID: 0037
Revises: 0036
Create Date: 2026-06-11

Adds the scoped autonomy-ladder policy table. Each row sets the autonomy
*level* (conservative / balanced / autonomous) for a workspace or a single
channel; resolution is channel -> workspace -> 'balanced'. Mirrors the
observe_policies scoping shape (unique per installation+scope_type+scope_id).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "autonomy_policies",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("installation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope_type", sa.String(), nullable=False),
        sa.Column("scope_id", sa.String(), nullable=True),
        sa.Column("level", sa.String(), nullable=False),
        sa.Column("updated_by_user_id", sa.String(), nullable=True),
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
            "scope_type in ('workspace', 'channel')",
            name="ck_autonomy_policies_scope_type",
        ),
        sa.CheckConstraint(
            "level in ('conservative', 'balanced', 'autonomous')",
            name="ck_autonomy_policies_level",
        ),
        sa.CheckConstraint(
            "(scope_type = 'workspace' and scope_id is null) or "
            "(scope_type = 'channel' and scope_id is not null)",
            name="ck_autonomy_policies_scope_id",
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"], ["installations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_autonomy_policies_scope_unique",
        "autonomy_policies",
        ["installation_id", "scope_type", sa.text("coalesce(scope_id, '')")],
        unique=True,
    )
    op.create_index(
        "idx_autonomy_policies_lookup",
        "autonomy_policies",
        ["installation_id", "scope_type", "scope_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_autonomy_policies_lookup", table_name="autonomy_policies")
    op.drop_index("idx_autonomy_policies_scope_unique", table_name="autonomy_policies")
    op.drop_table("autonomy_policies")
