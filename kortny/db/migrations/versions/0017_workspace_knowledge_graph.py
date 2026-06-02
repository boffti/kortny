"""workspace knowledge graph

Revision ID: 0017
Revises: 0016
Create Date: 2026-06-02

Adds a Postgres-native temporal entity/edge graph for HIG-181. This creates the
schema and indexes only; extraction, dashboard, and ADK runtime integration are
intentionally deferred.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

ENTITY_TYPES = (
    "'person', 'channel', 'project', 'firm_fact', 'artifact', 'decision', "
    "'open_question', 'commitment', 'integration', 'external_entity'"
)
RELATIONSHIP_TYPES = (
    "'member_of', 'maps_to', 'works_on', 'owns', 'belongs_to', "
    "'referenced_in', 'made_in', 'affects', 'relates_to', 'available_for'"
)
SCOPE_TYPES = "'workspace', 'channel', 'private_channel', 'dm', 'user'"
SOURCE_TYPES = (
    "'slack_authoritative', 'user_explicit', 'agent_inferred', "
    "'onboarding_scan', 'task_summary', 'integration_result', "
    "'workspace_state', 'admin_import'"
)
LIFECYCLE_STATES = (
    "'candidate', 'active', 'confirmed', 'stale', 'superseded', "
    "'contradicted', 'archived', 'forgotten'"
)


def upgrade() -> None:
    op.create_table(
        "kg_entities",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("installation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("canonical_key", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("external_ref_type", sa.String(), nullable=True),
        sa.Column("external_ref_id", sa.String(), nullable=True),
        sa.Column(
            "attrs_json",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("visibility_scope_type", sa.String(), nullable=False),
        sa.Column("visibility_scope_id", sa.String(), nullable=True),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column(
            "confidence_score",
            sa.Numeric(4, 3),
            server_default=sa.text("0.500"),
            nullable=False,
        ),
        sa.Column("confidence_reason", sa.Text(), nullable=True),
        sa.Column(
            "lifecycle_state",
            sa.String(),
            server_default=sa.text("'candidate'"),
            nullable=False,
        ),
        sa.Column(
            "valid_from",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("valid_to", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "recorded_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expired_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "is_current",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("freshness_window_days", sa.Integer(), nullable=True),
        sa.Column("last_reinforced_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "reinforcement_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
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
            f"entity_type in ({ENTITY_TYPES})",
            name="ck_kg_entities_type",
        ),
        sa.CheckConstraint(
            f"visibility_scope_type in ({SCOPE_TYPES})",
            name="ck_kg_entities_visibility_scope_type",
        ),
        sa.CheckConstraint(
            "(visibility_scope_type = 'workspace' and visibility_scope_id is null) or "
            "(visibility_scope_type in ('channel', 'private_channel', 'dm', 'user') "
            "and visibility_scope_id is not null)",
            name="ck_kg_entities_visibility_scope_id",
        ),
        sa.CheckConstraint(
            f"source_type in ({SOURCE_TYPES})",
            name="ck_kg_entities_source_type",
        ),
        sa.CheckConstraint(
            f"lifecycle_state in ({LIFECYCLE_STATES})",
            name="ck_kg_entities_lifecycle_state",
        ),
        sa.CheckConstraint(
            "confidence_score >= 0 and confidence_score <= 1",
            name="ck_kg_entities_confidence_score",
        ),
        sa.CheckConstraint(
            "reinforcement_count >= 0",
            name="ck_kg_entities_reinforcement_count",
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"], ["installations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_kg_entities_current_unique_key",
        "kg_entities",
        ["installation_id", "canonical_key"],
        unique=True,
        postgresql_where=sa.text("is_current = true AND expired_at IS NULL"),
    )
    op.create_index(
        "idx_kg_entities_lookup",
        "kg_entities",
        ["installation_id", "entity_type", "lifecycle_state", "is_current"],
    )
    op.create_index(
        "idx_kg_entities_scope",
        "kg_entities",
        ["installation_id", "visibility_scope_type", "visibility_scope_id"],
    )
    op.create_index(
        "idx_kg_entities_external_ref",
        "kg_entities",
        ["external_ref_type", "external_ref_id"],
    )
    op.create_index(
        "idx_kg_entities_attrs",
        "kg_entities",
        ["attrs_json"],
        postgresql_using="gin",
    )

    op.create_table(
        "kg_edges",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("installation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relationship_type", sa.String(), nullable=False),
        sa.Column(
            "attrs_json",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("visibility_scope_type", sa.String(), nullable=False),
        sa.Column("visibility_scope_id", sa.String(), nullable=True),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column(
            "confidence_score",
            sa.Numeric(4, 3),
            server_default=sa.text("0.500"),
            nullable=False,
        ),
        sa.Column("confidence_reason", sa.Text(), nullable=True),
        sa.Column(
            "lifecycle_state",
            sa.String(),
            server_default=sa.text("'candidate'"),
            nullable=False,
        ),
        sa.Column(
            "valid_from",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("valid_to", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "recorded_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expired_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "is_current",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("freshness_window_days", sa.Integer(), nullable=True),
        sa.Column("last_reinforced_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "reinforcement_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
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
            f"relationship_type in ({RELATIONSHIP_TYPES})",
            name="ck_kg_edges_relationship_type",
        ),
        sa.CheckConstraint(
            f"visibility_scope_type in ({SCOPE_TYPES})",
            name="ck_kg_edges_visibility_scope_type",
        ),
        sa.CheckConstraint(
            "(visibility_scope_type = 'workspace' and visibility_scope_id is null) or "
            "(visibility_scope_type in ('channel', 'private_channel', 'dm', 'user') "
            "and visibility_scope_id is not null)",
            name="ck_kg_edges_visibility_scope_id",
        ),
        sa.CheckConstraint(
            f"source_type in ({SOURCE_TYPES})",
            name="ck_kg_edges_source_type",
        ),
        sa.CheckConstraint(
            f"lifecycle_state in ({LIFECYCLE_STATES})",
            name="ck_kg_edges_lifecycle_state",
        ),
        sa.CheckConstraint(
            "confidence_score >= 0 and confidence_score <= 1",
            name="ck_kg_edges_confidence_score",
        ),
        sa.CheckConstraint(
            "reinforcement_count >= 0",
            name="ck_kg_edges_reinforcement_count",
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"], ["installations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_entity_id"], ["kg_entities.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["target_entity_id"], ["kg_entities.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_kg_edges_current_unique",
        "kg_edges",
        [
            "installation_id",
            "source_entity_id",
            "target_entity_id",
            "relationship_type",
            "visibility_scope_type",
            sa.text("coalesce(visibility_scope_id, '')"),
        ],
        unique=True,
        postgresql_where=sa.text("is_current = true AND expired_at IS NULL"),
    )
    op.create_index(
        "idx_kg_edges_source_lookup",
        "kg_edges",
        ["installation_id", "source_entity_id", "relationship_type", "is_current"],
    )
    op.create_index(
        "idx_kg_edges_target_lookup",
        "kg_edges",
        ["installation_id", "target_entity_id", "relationship_type", "is_current"],
    )
    op.create_index(
        "idx_kg_edges_scope",
        "kg_edges",
        ["installation_id", "visibility_scope_type", "visibility_scope_id"],
    )
    op.create_index(
        "idx_kg_edges_attrs",
        "kg_edges",
        ["attrs_json"],
        postgresql_using="gin",
    )

    op.create_table(
        "kg_evidence",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("installation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_kind", sa.String(), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("source_task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_episode_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_task_event_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "source_observation_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("source_slack_channel_id", sa.String(), nullable=True),
        sa.Column("source_slack_message_ts", sa.String(), nullable=True),
        sa.Column("source_slack_file_id", sa.String(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("extracted_by", sa.String(), nullable=False),
        sa.Column("raw_snippet", sa.Text(), nullable=True),
        sa.Column("confidence_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("confidence_reason", sa.Text(), nullable=True),
        sa.Column(
            "consensus_count",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "target_kind in ('entity', 'edge')",
            name="ck_kg_evidence_target_kind",
        ),
        sa.CheckConstraint(
            f"source_type in ({SOURCE_TYPES})",
            name="ck_kg_evidence_source_type",
        ),
        sa.CheckConstraint(
            "consensus_count > 0",
            name="ck_kg_evidence_consensus_count",
        ),
        sa.CheckConstraint(
            "confidence_score is null or "
            "(confidence_score >= 0 and confidence_score <= 1)",
            name="ck_kg_evidence_confidence_score",
        ),
        sa.CheckConstraint(
            "source_type = 'admin_import' or "
            "source_task_id is not null or "
            "source_episode_id is not null or "
            "source_task_event_id is not null or "
            "source_observation_id is not null or "
            "source_slack_channel_id is not null or "
            "source_slack_file_id is not null or "
            "source_url is not null",
            name="ck_kg_evidence_source_reference",
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"], ["installations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["source_task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["source_episode_id"], ["episodes.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["source_task_event_id"], ["task_events.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["source_observation_id"], ["observation_events.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_kg_evidence_target",
        "kg_evidence",
        ["target_kind", "target_id"],
    )
    op.create_index("idx_kg_evidence_task", "kg_evidence", ["source_task_id"])
    op.create_index("idx_kg_evidence_episode", "kg_evidence", ["source_episode_id"])
    op.create_index(
        "idx_kg_evidence_observation",
        "kg_evidence",
        ["source_observation_id"],
    )
    op.create_index(
        "idx_kg_evidence_slack_message",
        "kg_evidence",
        ["installation_id", "source_slack_channel_id", "source_slack_message_ts"],
    )


def downgrade() -> None:
    op.drop_index("idx_kg_evidence_slack_message", table_name="kg_evidence")
    op.drop_index("idx_kg_evidence_observation", table_name="kg_evidence")
    op.drop_index("idx_kg_evidence_episode", table_name="kg_evidence")
    op.drop_index("idx_kg_evidence_task", table_name="kg_evidence")
    op.drop_index("idx_kg_evidence_target", table_name="kg_evidence")
    op.drop_table("kg_evidence")

    op.drop_index("idx_kg_edges_attrs", table_name="kg_edges")
    op.drop_index("idx_kg_edges_scope", table_name="kg_edges")
    op.drop_index("idx_kg_edges_target_lookup", table_name="kg_edges")
    op.drop_index("idx_kg_edges_source_lookup", table_name="kg_edges")
    op.drop_index("idx_kg_edges_current_unique", table_name="kg_edges")
    op.drop_table("kg_edges")

    op.drop_index("idx_kg_entities_attrs", table_name="kg_entities")
    op.drop_index("idx_kg_entities_external_ref", table_name="kg_entities")
    op.drop_index("idx_kg_entities_scope", table_name="kg_entities")
    op.drop_index("idx_kg_entities_lookup", table_name="kg_entities")
    op.drop_index("idx_kg_entities_current_unique_key", table_name="kg_entities")
    op.drop_table("kg_entities")
