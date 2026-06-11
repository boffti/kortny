"""Reserved revision for HIG-231 (superseded; intentionally a no-op).

Revision ID: 0033
Revises: 0032
Create Date: 2026-06-11

This revision originally widened the ``witness_delivery_log`` decision check
constraint for HIG-231. Migration 0034 (HIG-198 + HIG-230) revises this id
and redefines the same constraint wholesale, so the HIG-231 widening moved to
0035 to keep one linear, last-writer-wins chain. Kept as a no-op to preserve
the revision chain.
"""

# revision identifiers
revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
