"""procedural skills registry

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-26

Adds the durable procedural-memory spine for built-in skills. Runtime use is
limited to system-owned, instruction-only skills in the first slice.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "procedural_skills",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("owner_type", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("trust_level", sa.String(), nullable=False),
        sa.Column("visibility", sa.String(), nullable=False),
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
            "owner_type in ('system', 'workspace', 'user')",
            name="ck_procedural_skills_owner_type",
        ),
        sa.CheckConstraint(
            "status in ('draft', 'active', 'deprecated', 'disabled', 'archived')",
            name="ck_procedural_skills_status",
        ),
        sa.CheckConstraint(
            "trust_level in ('trusted', 'reviewed', 'unreviewed', 'quarantined')",
            name="ck_procedural_skills_trust_level",
        ),
        sa.CheckConstraint(
            "visibility in ('catalog', 'explicit_only', 'disabled')",
            name="ck_procedural_skills_visibility",
        ),
        sa.CheckConstraint(
            "(owner_type = 'system' and owner_id is null) or "
            "(owner_type in ('workspace', 'user') and owner_id is not null)",
            name="ck_procedural_skills_owner_id",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_procedural_skills_unique_slug",
        "procedural_skills",
        ["owner_type", sa.text("coalesce(owner_id, '')"), "slug"],
        unique=True,
    )
    op.create_index(
        "idx_procedural_skills_catalog",
        "procedural_skills",
        ["owner_type", "status", "visibility", "slug"],
    )

    op.create_table(
        "procedural_skill_versions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("skill_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("instructions_md", sa.Text(), nullable=False),
        sa.Column(
            "intent_tags",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "response_modes",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "trigger_phrases",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "allowed_tools",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("content_sha256", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("approved_by", sa.String(), nullable=True),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
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
            "status in ('draft', 'active', 'deprecated', 'archived')",
            name="ck_procedural_skill_versions_status",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["procedural_skills.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "skill_id",
            "version",
            name="idx_procedural_skill_versions_unique",
        ),
    )
    op.create_index(
        "idx_procedural_skill_versions_active",
        "procedural_skill_versions",
        ["skill_id", "status", "version"],
    )
    op.create_index(
        "idx_procedural_skill_versions_tags",
        "procedural_skill_versions",
        ["intent_tags"],
        postgresql_using="gin",
    )
    op.create_index(
        "idx_procedural_skill_versions_modes",
        "procedural_skill_versions",
        ["response_modes"],
        postgresql_using="gin",
    )

    op.create_table(
        "procedural_skill_invocations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("installation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("skill_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("skill_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invocation_kind", sa.String(), nullable=False),
        sa.Column("response_mode", sa.String(), nullable=True),
        sa.Column("selected_reason", sa.Text(), nullable=True),
        sa.Column(
            "payload",
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
        sa.ForeignKeyConstraint(
            ["installation_id"], ["installations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["procedural_skills.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["skill_version_id"],
            ["procedural_skill_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_procedural_skill_invocations_task",
        "procedural_skill_invocations",
        ["task_id", "created_at"],
    )
    op.create_index(
        "idx_procedural_skill_invocations_skill",
        "procedural_skill_invocations",
        ["skill_id", "skill_version_id", "created_at"],
    )
    op.create_index(
        "idx_procedural_skill_invocations_installation",
        "procedural_skill_invocations",
        ["installation_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_procedural_skill_invocations_installation",
        table_name="procedural_skill_invocations",
    )
    op.drop_index(
        "idx_procedural_skill_invocations_skill",
        table_name="procedural_skill_invocations",
    )
    op.drop_index(
        "idx_procedural_skill_invocations_task",
        table_name="procedural_skill_invocations",
    )
    op.drop_table("procedural_skill_invocations")

    op.drop_index(
        "idx_procedural_skill_versions_modes",
        table_name="procedural_skill_versions",
    )
    op.drop_index(
        "idx_procedural_skill_versions_tags",
        table_name="procedural_skill_versions",
    )
    op.drop_index(
        "idx_procedural_skill_versions_active",
        table_name="procedural_skill_versions",
    )
    op.drop_table("procedural_skill_versions")

    op.drop_index("idx_procedural_skills_catalog", table_name="procedural_skills")
    op.drop_index("idx_procedural_skills_unique_slug", table_name="procedural_skills")
    op.drop_table("procedural_skills")
