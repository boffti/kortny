"""Skill directory: provenance, trust ladder, bundled files, scoped enablements.

Revision ID: 0026
Revises: 0025
Create Date: 2026-06-09

Extends the procedural skill registry for the dashboard skills directory
(HIG-189): provenance tracking, the trusted/community/untrusted trust ladder,
bundled SKILL.md resource files, and per-scope (workspace/channel/user)
enablements.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "procedural_skills",
        sa.Column(
            "provenance",
            sa.String(),
            nullable=False,
            server_default="kortny",
        ),
    )

    op.execute(
        "UPDATE procedural_skills SET trust_level = 'community' "
        "WHERE trust_level = 'reviewed'"
    )
    op.execute(
        "UPDATE procedural_skills SET trust_level = 'untrusted' "
        "WHERE trust_level = 'unreviewed'"
    )
    op.drop_constraint(
        "ck_procedural_skills_trust_level",
        "procedural_skills",
        type_="check",
    )
    op.create_check_constraint(
        "ck_procedural_skills_trust_level",
        "procedural_skills",
        "trust_level in ('trusted', 'community', 'untrusted', 'quarantined')",
    )

    op.create_table(
        "skill_files",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "skill_version_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("content_bytes", sa.LargeBinary(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind in ('reference', 'asset', 'script')",
            name="ck_skill_files_kind",
        ),
        sa.ForeignKeyConstraint(
            ["skill_version_id"],
            ["procedural_skill_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "skill_version_id",
            "path",
            name="uq_skill_files_version_path",
        ),
    )
    op.create_index(
        "idx_skill_files_version",
        "skill_files",
        ["skill_version_id", "kind"],
    )

    op.create_table(
        "skill_enablements",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "installation_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "skill_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("scope_type", sa.String(), nullable=False),
        sa.Column("scope_id", sa.String(), nullable=True),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default="enabled",
        ),
        sa.Column("added_by", sa.String(), nullable=False),
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
            "scope_type in ('workspace', 'channel', 'user')",
            name="ck_skill_enablements_scope_type",
        ),
        sa.CheckConstraint(
            "status in ('enabled', 'disabled')",
            name="ck_skill_enablements_status",
        ),
        sa.CheckConstraint(
            "(scope_type = 'workspace' and scope_id is null) or "
            "(scope_type in ('channel', 'user') and scope_id is not null)",
            name="ck_skill_enablements_scope_id",
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"],
            ["installations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"],
            ["procedural_skills.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_skill_enablements_unique",
        "skill_enablements",
        [
            "installation_id",
            "skill_id",
            "scope_type",
            sa.text("coalesce(scope_id, '')"),
        ],
        unique=True,
    )
    op.create_index(
        "idx_skill_enablements_scope",
        "skill_enablements",
        ["installation_id", "scope_type", "scope_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("idx_skill_enablements_scope", table_name="skill_enablements")
    op.drop_index("idx_skill_enablements_unique", table_name="skill_enablements")
    op.drop_table("skill_enablements")
    op.drop_index("idx_skill_files_version", table_name="skill_files")
    op.drop_table("skill_files")

    op.execute(
        "UPDATE procedural_skills SET trust_level = 'reviewed' "
        "WHERE trust_level = 'community'"
    )
    op.execute(
        "UPDATE procedural_skills SET trust_level = 'unreviewed' "
        "WHERE trust_level = 'untrusted'"
    )
    op.drop_constraint(
        "ck_procedural_skills_trust_level",
        "procedural_skills",
        type_="check",
    )
    op.create_check_constraint(
        "ck_procedural_skills_trust_level",
        "procedural_skills",
        "trust_level in ('trusted', 'reviewed', 'unreviewed', 'quarantined')",
    )
    op.drop_column("procedural_skills", "provenance")
