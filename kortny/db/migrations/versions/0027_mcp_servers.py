"""MCP servers: admin-registered Model Context Protocol servers + cached tools.

Revision ID: 0027
Revises: 0026
Create Date: 2026-06-10

Backs HIG-207. Admins register MCP servers (stdio / streamable_http / sse) from
the dashboard. Server tools are discovered at registration time and cached in
``mcp_server_tools`` so per-task selection stays flat-latency. Non-secret env /
headers live in JSONB columns; secret values are stored encrypted in
``secret_env`` via ``kortny.secrets.encrypt_secret_value``.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_servers",
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
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("transport", sa.String(), nullable=False),
        sa.Column("command", sa.String(), nullable=True),
        sa.Column(
            "args",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column(
            "env_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "headers_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("secret_env", postgresql.BYTEA(), nullable=True),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default="enabled",
        ),
        sa.Column("last_discovery_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_discovery_error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=False),
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
            "transport in ('stdio', 'streamable_http', 'sse')",
            name="ck_mcp_servers_transport",
        ),
        sa.CheckConstraint(
            "status in ('enabled', 'disabled')",
            name="ck_mcp_servers_status",
        ),
        sa.CheckConstraint(
            "(transport = 'stdio' and command is not null) or "
            "(transport in ('streamable_http', 'sse') and url is not null)",
            name="ck_mcp_servers_transport_target",
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"],
            ["installations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "installation_id",
            "name",
            name="uq_mcp_servers_installation_name",
        ),
    )
    op.create_index(
        "idx_mcp_servers_enabled_lookup",
        "mcp_servers",
        ["installation_id", "status"],
    )

    op.create_table(
        "mcp_server_tools",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "server_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "description",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "input_schema",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("read_only_hint", sa.Boolean(), nullable=True),
        sa.Column("destructive_hint", sa.Boolean(), nullable=True),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
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
        sa.ForeignKeyConstraint(
            ["server_id"],
            ["mcp_servers.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "server_id",
            "name",
            name="uq_mcp_server_tools_server_name",
        ),
    )
    op.create_index(
        "idx_mcp_server_tools_enabled_lookup",
        "mcp_server_tools",
        ["server_id", "enabled"],
    )


def downgrade() -> None:
    op.drop_index("idx_mcp_server_tools_enabled_lookup", table_name="mcp_server_tools")
    op.drop_table("mcp_server_tools")
    op.drop_index("idx_mcp_servers_enabled_lookup", table_name="mcp_servers")
    op.drop_table("mcp_servers")
