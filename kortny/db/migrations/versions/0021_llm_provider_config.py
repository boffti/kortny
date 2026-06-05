"""llm provider configuration registry

Revision ID: 0021
Revises: 0020
Create Date: 2026-06-04

Add the DB-owned provider/model/tier/pricing/audit tables needed for
dashboard-managed LLM routing while preserving env-backed bootstrapping.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_provider_accounts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("installation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_kind", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.String(),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column(
            "health_status",
            sa.String(),
            server_default=sa.text("'unknown'"),
            nullable=False,
        ),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("encrypted_secret_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status in ('active', 'disabled', 'testing')",
            name="ck_llm_provider_accounts_status",
        ),
        sa.CheckConstraint(
            "health_status in ('ok', 'degraded', 'down', 'unknown')",
            name="ck_llm_provider_accounts_health_status",
        ),
        sa.ForeignKeyConstraint(
            ["encrypted_secret_id"], ["encrypted_secrets.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"], ["installations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_llm_provider_accounts_installation",
        "llm_provider_accounts",
        ["installation_id", "status"],
    )
    op.create_index(
        "idx_llm_provider_accounts_kind",
        "llm_provider_accounts",
        ["installation_id", "provider_kind"],
    )

    op.create_table(
        "llm_model_catalog",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("provider_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_identifier", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "capabilities_json",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "source",
            sa.String(),
            server_default=sa.text("'manual'"),
            nullable=False,
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source in ('manual', 'env_bootstrap', 'litellm_catalog', 'provider_api')",
            name="ck_llm_model_catalog_source",
        ),
        sa.ForeignKeyConstraint(
            ["provider_account_id"], ["llm_provider_accounts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider_account_id",
            "model_identifier",
            name="idx_llm_model_catalog_provider_model",
        ),
    )
    op.create_index(
        "idx_llm_model_catalog_enabled",
        "llm_model_catalog",
        ["provider_account_id", "is_enabled"],
    )

    op.create_table(
        "llm_tier_assignments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("installation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tier", sa.String(), nullable=False),
        sa.Column("model_catalog_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "priority",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "routing_json",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "tier in ('cheap_fast', 'standard', 'analysis', 'document', "
            "'high_reasoning')",
            name="ck_llm_tier_assignments_tier",
        ),
        sa.CheckConstraint("priority >= 1", name="ck_llm_tier_assignments_priority"),
        sa.ForeignKeyConstraint(
            ["installation_id"], ["installations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["model_catalog_id"], ["llm_model_catalog.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "installation_id",
            "tier",
            "priority",
            name="idx_llm_tier_assignment_priority",
        ),
    )
    op.create_index(
        "idx_llm_tier_assignments_active",
        "llm_tier_assignments",
        ["installation_id", "tier", "is_active"],
    )

    op.create_table(
        "llm_model_pricing",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("provider_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_identifier", sa.String(), nullable=False),
        sa.Column("input_price_per_mtok", sa.Numeric(12, 6), nullable=True),
        sa.Column("output_price_per_mtok", sa.Numeric(12, 6), nullable=True),
        sa.Column(
            "currency",
            sa.String(),
            server_default=sa.text("'USD'"),
            nullable=False,
        ),
        sa.Column("pricing_source", sa.String(), nullable=False),
        sa.Column(
            "effective_from",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["provider_account_id"], ["llm_provider_accounts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider_account_id",
            "model_identifier",
            "effective_from",
            name="idx_llm_model_pricing_lookup",
        ),
    )
    op.create_index(
        "idx_llm_model_pricing_model",
        "llm_model_pricing",
        ["provider_account_id", "model_identifier"],
    )

    op.create_table(
        "llm_budget_policies",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("installation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tier", sa.String(), nullable=True),
        sa.Column("daily_budget_usd", sa.Numeric(12, 2), nullable=True),
        sa.Column("monthly_budget_usd", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "alert_threshold_pct",
            sa.Integer(),
            server_default=sa.text("80"),
            nullable=False,
        ),
        sa.Column(
            "behavior",
            sa.String(),
            server_default=sa.text("'soft_stop'"),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "tier is null or tier in ('cheap_fast', 'standard', 'analysis', "
            "'document', 'high_reasoning')",
            name="ck_llm_budget_policies_tier",
        ),
        sa.CheckConstraint(
            "alert_threshold_pct between 1 and 100",
            name="ck_llm_budget_policies_alert_threshold",
        ),
        sa.CheckConstraint(
            "behavior in ('soft_stop', 'hard_stop')",
            name="ck_llm_budget_policies_behavior",
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"], ["installations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_llm_budget_policies_installation",
        "llm_budget_policies",
        ["installation_id", "is_active"],
    )

    op.create_table(
        "llm_config_audit",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("installation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_slack_user_id", sa.String(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=True),
        sa.Column("previous_value", postgresql.JSONB(), nullable=True),
        sa.Column("new_value", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action in ('create', 'update', 'disable', 'enable', 'delete', "
            "'bootstrap')",
            name="ck_llm_config_audit_action",
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"], ["installations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_llm_config_audit_installation",
        "llm_config_audit",
        ["installation_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_llm_config_audit_installation", table_name="llm_config_audit")
    op.drop_table("llm_config_audit")

    op.drop_index(
        "idx_llm_budget_policies_installation", table_name="llm_budget_policies"
    )
    op.drop_table("llm_budget_policies")

    op.drop_index("idx_llm_model_pricing_model", table_name="llm_model_pricing")
    op.drop_table("llm_model_pricing")

    op.drop_index("idx_llm_tier_assignments_active", table_name="llm_tier_assignments")
    op.drop_table("llm_tier_assignments")

    op.drop_index("idx_llm_model_catalog_enabled", table_name="llm_model_catalog")
    op.drop_table("llm_model_catalog")

    op.drop_index("idx_llm_provider_accounts_kind", table_name="llm_provider_accounts")
    op.drop_index(
        "idx_llm_provider_accounts_installation", table_name="llm_provider_accounts"
    )
    op.drop_table("llm_provider_accounts")
