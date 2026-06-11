"""Allow the HIG-231 ambient_file_brief decision in witness_delivery_log.

Revision ID: 0035
Revises: 0034
Create Date: 2026-06-11

Backs HIG-231 (ambient file analysis). Ambient file briefs share the weekly
per-channel proactivity window with HIG-198 channel posts: both account
through ``witness_delivery_log`` rows keyed ``channel:{channel_id}`` in
``slack_user_id``. HIG-231 writes ``decision='ambient_file_brief'`` at task
creation time and counts ``ambient_file_brief`` + ``channel_sent`` rows when
enforcing the weekly budget. This migration adds ``ambient_file_brief`` to
the decision set established by 0034.

No table or column changes — only the check constraint is widened.
"""

from alembic import op

# revision identifiers
revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None

PRIOR_DECISIONS = (
    "'notify', 'question', 'draft', 'silent', 'digest', "
    "'channel_sent', 'channel_deferred', 'draft_executed'"
)
WIDENED_DECISIONS = PRIOR_DECISIONS + ", 'ambient_file_brief'"


def upgrade() -> None:
    op.drop_constraint(
        "ck_witness_delivery_log_decision",
        "witness_delivery_log",
        type_="check",
    )
    op.create_check_constraint(
        "ck_witness_delivery_log_decision",
        "witness_delivery_log",
        f"decision in ({WIDENED_DECISIONS})",
    )


def downgrade() -> None:
    op.execute("DELETE FROM witness_delivery_log WHERE decision = 'ambient_file_brief'")
    op.drop_constraint(
        "ck_witness_delivery_log_decision",
        "witness_delivery_log",
        type_="check",
    )
    op.create_check_constraint(
        "ck_witness_delivery_log_decision",
        "witness_delivery_log",
        f"decision in ({PRIOR_DECISIONS})",
    )
