"""schedule proposals

Revision ID: 0019
Revises: 0018
Create Date: 2026-06-04

Allow schedules to be captured as proposed candidates before they become active.
"""

from alembic import op

# revision identifiers
revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_schedules_status", "schedules", type_="check")
    op.create_check_constraint(
        "ck_schedules_status",
        "schedules",
        "status in ('proposed', 'active', 'paused', 'completed', 'cancelled')",
    )


def downgrade() -> None:
    op.execute("UPDATE schedules SET status = 'paused' WHERE status = 'proposed'")
    op.drop_constraint("ck_schedules_status", "schedules", type_="check")
    op.create_check_constraint(
        "ck_schedules_status",
        "schedules",
        "status in ('active', 'paused', 'completed', 'cancelled')",
    )
