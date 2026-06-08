"""Allow Slack canvas side effect operations.

Revision ID: 0025
Revises: 0024
Create Date: 2026-06-07 22:45:00.000000
"""

from __future__ import annotations

from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

UPGRADE_OPERATIONS = (
    "'chat_postMessage', 'files_upload_v2', 'reactions_add', "
    "'reactions_remove', 'pins_add', 'bookmarks_add', "
    "'conversations_canvases_create', 'canvases_edit'"
)
DOWNGRADE_OPERATIONS = (
    "'chat_postMessage', 'files_upload_v2', 'reactions_add', "
    "'reactions_remove', 'pins_add', 'bookmarks_add'"
)


def upgrade() -> None:
    op.drop_constraint(
        "ck_slack_side_effects_operation",
        "slack_side_effects",
        type_="check",
    )
    op.create_check_constraint(
        "ck_slack_side_effects_operation",
        "slack_side_effects",
        f"operation in ({UPGRADE_OPERATIONS})",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_slack_side_effects_operation",
        "slack_side_effects",
        type_="check",
    )
    op.create_check_constraint(
        "ck_slack_side_effects_operation",
        "slack_side_effects",
        f"operation in ({DOWNGRADE_OPERATIONS})",
    )
