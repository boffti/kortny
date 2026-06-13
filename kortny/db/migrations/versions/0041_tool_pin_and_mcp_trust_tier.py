"""Tool schema pinning + MCP server trust tier (HIG-169 P0).

Revision ID: 0041
Revises: 0040
Create Date: 2026-06-12

Deterministic prompt-injection / tool-trust baseline:

* ``mcp_servers.trust_tier`` — trusted/community/untrusted ladder (mirrors the
  skills trust ladder). ``readOnlyHint`` is attacker-asserted metadata, so the
  read-only approval bypass is honored only for trusted, pinned-unchanged MCP
  tools. Existing rows backfill to ``untrusted`` (conservative); the column is
  NOT NULL with a server default so this is columns-only on ``mcp_servers``.
* ``tool_pins`` — one pinned schema fingerprint per external tool (MCP /
  Composio). The fingerprint includes the tool's ``inputSchema`` (the rug-pull
  surface the existing ``card_sha`` / ``description_sha256`` columns omit). When
  the live fingerprint drifts, ``status`` flips to ``drifted`` and the read-only
  bypass is revoked until an admin re-pins.

Hand-written per the 0039/0040 pattern. This adds the ``tool_pins`` table, so
the exact-table-set assertion in tests/test_db_models.py is updated alongside.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE mcp_servers "
        "ADD COLUMN IF NOT EXISTS trust_tier varchar "
        "NOT NULL DEFAULT 'untrusted'"
    )
    op.execute(
        "ALTER TABLE mcp_servers DROP CONSTRAINT IF EXISTS ck_mcp_servers_trust_tier"
    )
    op.execute(
        "ALTER TABLE mcp_servers "
        "ADD CONSTRAINT ck_mcp_servers_trust_tier "
        "CHECK (trust_tier in ('trusted', 'community', 'untrusted'))"
    )

    op.create_table(
        "tool_pins",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "installation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("installations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("server_ref", sa.String(), nullable=False),
        sa.Column("tool_name", sa.String(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("prior_description", sa.Text(), nullable=True),
        sa.Column(
            "prior_schema_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default="active",
        ),
        sa.Column("approved_by", sa.String(), nullable=True),
        sa.Column(
            "approved_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "provider in ('mcp', 'composio')",
            name="ck_tool_pins_provider",
        ),
        sa.CheckConstraint(
            "status in ('active', 'drifted')",
            name="ck_tool_pins_status",
        ),
        sa.UniqueConstraint(
            "installation_id",
            "provider",
            "server_ref",
            "tool_name",
            name="uq_tool_pins_identity",
        ),
    )
    op.create_index(
        "idx_tool_pins_lookup",
        "tool_pins",
        ["installation_id", "provider", "server_ref"],
    )


def downgrade() -> None:
    op.drop_index("idx_tool_pins_lookup", table_name="tool_pins")
    op.drop_table("tool_pins")
    op.execute(
        "ALTER TABLE mcp_servers DROP CONSTRAINT IF EXISTS ck_mcp_servers_trust_tier"
    )
    op.execute("ALTER TABLE mcp_servers DROP COLUMN IF EXISTS trust_tier")
