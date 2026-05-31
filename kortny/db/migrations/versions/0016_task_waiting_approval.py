"""task waiting approval status

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-31

Adds a non-terminal task state for human-in-the-loop approval waits.
"""

from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


OLD_TASK_STATUSES = (
    "pending",
    "running",
    "succeeded",
    "failed",
    "crashed",
    "cancelled",
)


def upgrade() -> None:
    op.execute("ALTER TYPE task_status ADD VALUE IF NOT EXISTS 'waiting_approval'")


def downgrade() -> None:
    op.execute("UPDATE tasks SET status = 'pending' WHERE status = 'waiting_approval'")
    op.execute("ALTER TYPE task_status RENAME TO task_status_old")
    task_status = postgresql.ENUM(*OLD_TASK_STATUSES, name="task_status")
    task_status.create(op.get_bind(), checkfirst=False)
    op.execute("ALTER TABLE tasks ALTER COLUMN status DROP DEFAULT")
    op.execute(
        "ALTER TABLE tasks ALTER COLUMN status TYPE task_status "
        "USING status::text::task_status"
    )
    op.execute(
        "ALTER TABLE tasks ALTER COLUMN status SET DEFAULT 'pending'::task_status"
    )
    op.execute("DROP TYPE task_status_old")
