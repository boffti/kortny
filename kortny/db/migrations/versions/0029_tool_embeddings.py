"""Tool embeddings: pgvector-backed semantic index for tool cards and skills.

Revision ID: 0029
Revises: 0028
Create Date: 2026-06-10

Backs HIG-219 (Capability Fabric). Creates the ``vector`` extension and a
``tool_embeddings`` table that stores one embedding per (kind, ref_key, model).
``embedding`` is an untyped ``vector`` column so rows produced by models with
different dimensions can coexist; queries cast the query vector at runtime.

The downgrade drops only the table — the extension stays installed because
other databases/objects may depend on it.
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "tool_embeddings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("ref_key", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("embedding", Vector(), nullable=False),
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
            "kind in ('tool_card', 'skill')",
            name="ck_tool_embeddings_kind",
        ),
        sa.UniqueConstraint(
            "kind",
            "ref_key",
            "model",
            name="uq_tool_embeddings_kind_ref_key_model",
        ),
    )
    op.create_index(
        "idx_tool_embeddings_kind_model",
        "tool_embeddings",
        ["kind", "model"],
    )
    # No ANN index: the catalog stays in the hundreds of rows, where an exact
    # scan is both correct and fast.


def downgrade() -> None:
    op.drop_index("idx_tool_embeddings_kind_model", table_name="tool_embeddings")
    op.drop_table("tool_embeddings")
    # Intentionally leave the vector extension installed.
