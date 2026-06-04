"""postgres-native schedules

Revision ID: 0018
Revises: 0017
Create Date: 2026-06-04

Adds the v1 scheduling source-of-truth table. Schedules materialize into normal
tasks rows; workers and the runtime remain responsible for execution.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "schedules",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("installation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_type", sa.String(), nullable=False),
        sa.Column("owner_slack_user_id", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("spec_kind", sa.String(), nullable=False),
        sa.Column("cron_expr", sa.String(), nullable=True),
        sa.Column("interval_seconds", sa.Integer(), nullable=True),
        sa.Column("run_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "timezone",
            sa.String(),
            server_default=sa.text("'UTC'"),
            nullable=False,
        ),
        sa.Column("next_run_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "catchup_policy",
            sa.String(),
            server_default=sa.text("'skip'"),
            nullable=False,
        ),
        sa.Column("catchup_window_seconds", sa.Integer(), nullable=True),
        sa.Column(
            "overlap_policy",
            sa.String(),
            server_default=sa.text("'skip'"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column(
            "task_template",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("planned_cost_ceiling_usd", sa.Numeric(10, 4), nullable=True),
        sa.Column("idempotency_key_template", sa.String(), nullable=True),
        sa.Column("created_by_slack_user_id", sa.String(), nullable=True),
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
            "owner_type in ('user', 'system')",
            name="ck_schedules_owner_type",
        ),
        sa.CheckConstraint(
            "(owner_type = 'user' and owner_slack_user_id is not null) or "
            "(owner_type = 'system')",
            name="ck_schedules_owner",
        ),
        sa.CheckConstraint(
            "spec_kind in ('oneoff', 'interval', 'cron')",
            name="ck_schedules_spec_kind",
        ),
        sa.CheckConstraint(
            "(spec_kind = 'oneoff' and run_at is not null) or "
            "(spec_kind = 'interval' and interval_seconds is not null and "
            "interval_seconds > 0) or "
            "(spec_kind = 'cron' and cron_expr is not null and cron_expr <> '')",
            name="ck_schedules_spec",
        ),
        sa.CheckConstraint(
            "catchup_policy in ('skip', 'run_once', 'backfill')",
            name="ck_schedules_catchup_policy",
        ),
        sa.CheckConstraint(
            "catchup_window_seconds is null or catchup_window_seconds >= 0",
            name="ck_schedules_catchup_window",
        ),
        sa.CheckConstraint(
            "overlap_policy in ('skip', 'allow')",
            name="ck_schedules_overlap_policy",
        ),
        sa.CheckConstraint(
            "status in ('active', 'paused', 'completed', 'cancelled')",
            name="ck_schedules_status",
        ),
        sa.CheckConstraint(
            "planned_cost_ceiling_usd is null or planned_cost_ceiling_usd > 0",
            name="ck_schedules_cost_ceiling",
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"], ["installations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_schedules_due",
        "schedules",
        ["next_run_at"],
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "idx_schedules_owner",
        "schedules",
        ["installation_id", "owner_type", "owner_slack_user_id", "status"],
    )
    op.create_index(
        "idx_schedules_status",
        "schedules",
        ["installation_id", "status", "next_run_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_schedules_status", table_name="schedules")
    op.drop_index("idx_schedules_owner", table_name="schedules")
    op.drop_index("idx_schedules_due", table_name="schedules")
    op.drop_table("schedules")
