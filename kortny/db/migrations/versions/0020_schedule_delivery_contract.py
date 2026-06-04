"""schedule delivery contract

Revision ID: 0020
Revises: 0019
Create Date: 2026-06-04

Promote scheduled-task delivery destination from template metadata into first
class columns so recurring Slack delivery can be reasoned about and audited.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "schedules",
        sa.Column(
            "delivery_kind",
            sa.String(),
            server_default=sa.text("'slack_dm'"),
            nullable=False,
        ),
    )
    op.add_column(
        "schedules",
        sa.Column("delivery_slack_user_id", sa.String(), nullable=True),
    )
    op.add_column(
        "schedules",
        sa.Column("delivery_slack_channel_id", sa.String(), nullable=True),
    )
    op.add_column(
        "schedules",
        sa.Column("delivery_slack_thread_ts", sa.String(), nullable=True),
    )
    op.add_column(
        "schedules",
        sa.Column(
            "artifact_delivery_policy",
            sa.String(),
            server_default=sa.text("'message_only'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_schedules_delivery_kind",
        "schedules",
        "delivery_kind in "
        "('slack_dm', 'slack_channel', 'slack_thread', 'dashboard_only')",
    )
    op.create_check_constraint(
        "ck_schedules_artifact_delivery_policy",
        "schedules",
        "artifact_delivery_policy in "
        "('message_only', 'attach_files', 'link_artifacts')",
    )
    op.execute(
        """
        UPDATE schedules
        SET
            delivery_kind = CASE
                WHEN task_template->>'delivery_surface' = 'thread'
                    THEN 'slack_thread'
                WHEN task_template->>'delivery_surface' = 'channel'
                    THEN 'slack_channel'
                WHEN task_template->>'delivery_surface' = 'dashboard'
                    THEN 'dashboard_only'
                ELSE 'slack_dm'
            END,
            delivery_slack_user_id = COALESCE(
                task_template->>'slack_user_id',
                owner_slack_user_id
            ),
            delivery_slack_channel_id = task_template->>'slack_channel_id',
            delivery_slack_thread_ts = task_template->>'slack_thread_ts'
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_schedules_artifact_delivery_policy",
        "schedules",
        type_="check",
    )
    op.drop_constraint("ck_schedules_delivery_kind", "schedules", type_="check")
    op.drop_column("schedules", "artifact_delivery_policy")
    op.drop_column("schedules", "delivery_slack_thread_ts")
    op.drop_column("schedules", "delivery_slack_channel_id")
    op.drop_column("schedules", "delivery_slack_user_id")
    op.drop_column("schedules", "delivery_kind")
