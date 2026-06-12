"""Witness frequency counting + cross-scan state (HIG-197 Phase 1).

Revision ID: 0039
Revises: 0038
Create Date: 2026-06-11

Backs HIG-197 Phase 1 (witness frequency counting). Ensures the
``witness_opportunity_candidates`` cross-scan reinforcement columns exist:
``reinforcement_count`` (NOT NULL, server default 1) and ``first_observed_at``
(timestamptz, nullable), with ``first_observed_at`` backfilled from
``created_at`` for existing rows.

These columns were introduced earlier by migration 0032 (HIG-227 Slice D); this
migration is written idempotently (``ADD COLUMN IF NOT EXISTS`` / guarded
backfill) so it is a safe no-op on any database where 0032 already ran, and
still establishes the HIG-197 contract on a database that lacks them. It does
not edit 0032.
"""

from alembic import op

# revision identifiers
revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE witness_opportunity_candidates "
        "ADD COLUMN IF NOT EXISTS reinforcement_count integer "
        "NOT NULL DEFAULT 1"
    )
    op.execute(
        "ALTER TABLE witness_opportunity_candidates "
        "ADD COLUMN IF NOT EXISTS first_observed_at timestamptz"
    )
    op.execute(
        "UPDATE witness_opportunity_candidates "
        "SET first_observed_at = created_at WHERE first_observed_at IS NULL"
    )
    # Frequency counts are never negative.
    op.execute(
        "ALTER TABLE witness_opportunity_candidates "
        "DROP CONSTRAINT IF EXISTS "
        "ck_witness_opportunity_candidates_reinforcement_count"
    )
    op.execute(
        "ALTER TABLE witness_opportunity_candidates "
        "ADD CONSTRAINT ck_witness_opportunity_candidates_reinforcement_count "
        "CHECK (reinforcement_count >= 0)"
    )


def downgrade() -> None:
    # The columns predate this migration (0032 owns them); only drop the
    # constraint this migration added so 0032's downgrade stays authoritative.
    op.execute(
        "ALTER TABLE witness_opportunity_candidates "
        "DROP CONSTRAINT IF EXISTS "
        "ck_witness_opportunity_candidates_reinforcement_count"
    )
