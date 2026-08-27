"""add API Registry (REST-backed MCP tools)

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-03

Extends the MCP Gateway so enterprise REST APIs can be exposed as MCP tools
alongside native MCP-server tools, per docs/api-registry.md:

- api_services: the REST API Service Registry (base_url, auth, headers,
  timeout, retry policy), the REST analogue of mcp_servers.
- api_endpoints: one registered REST endpoint per row (method, path,
  parameters), the REST analogue of a single tool definition; tool_name is
  unique gateway-wide, same rule as mcp_tools.name.
- mcp_tools gains source_type (mcp|rest) and api_endpoint_id, and server_id
  becomes nullable -- a tool now points at exactly one of an MCP server or a
  REST endpoint, enforced by chk_mcp_tool_source.
- mcp_request_logs gains execution_type/api_service_id/endpoint_path/status_code
  for REST-call observability (mirrors server_id for MCP calls).
- access_policies gains allowed_tool_names for tool-scoped RBAC/ABAC (e.g.
  "only finance agents can execute payment APIs").
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_services",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("base_url", sa.String(), nullable=False),
        sa.Column(
            "authentication_type",
            postgresql.ENUM(
                "none", "api_key", "bearer", "basic", "oauth2_client_credentials", name="rest_auth_type"
            ),
            nullable=False,
            server_default="none",
        ),
        sa.Column("auth_config", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("headers", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("timeout_seconds", sa.Float(), nullable=False, server_default="10.0"),
        sa.Column("retry_policy", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("rate_limit_per_window", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM("active", "inactive", name="api_service_status"),
            nullable=False,
            server_default="active",
        ),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "api_endpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "api_service_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("api_services.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tool_name", sa.String(), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("method", postgresql.ENUM("GET", "POST", "PUT", "DELETE", name="rest_http_method"), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("parameters", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_api_endpoints_api_service_id", "api_endpoints", ["api_service_id"])

    mcp_tool_source_type = postgresql.ENUM("mcp", "rest", name="mcp_tool_source_type")
    mcp_tool_source_type.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "mcp_tools",
        sa.Column(
            "source_type",
            postgresql.ENUM("mcp", "rest", name="mcp_tool_source_type", create_type=False),
            nullable=False,
            server_default="mcp",
        ),
    )
    op.add_column(
        "mcp_tools",
        sa.Column(
            "api_endpoint_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("api_endpoints.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.alter_column("mcp_tools", "server_id", nullable=True)
    op.create_check_constraint(
        "chk_mcp_tool_source",
        "mcp_tools",
        "(source_type = 'mcp' AND server_id IS NOT NULL AND api_endpoint_id IS NULL) OR "
        "(source_type = 'rest' AND api_endpoint_id IS NOT NULL AND server_id IS NULL)",
    )

    op.add_column(
        "mcp_request_logs",
        sa.Column(
            "execution_type",
            postgresql.ENUM("mcp", "rest", name="mcp_tool_source_type", create_type=False),
            nullable=True,
        ),
    )
    op.add_column(
        "mcp_request_logs",
        sa.Column(
            "api_service_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("api_services.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("mcp_request_logs", sa.Column("endpoint_path", sa.String(), nullable=True))
    op.add_column("mcp_request_logs", sa.Column("status_code", sa.Integer(), nullable=True))

    op.add_column(
        "access_policies",
        sa.Column("allowed_tool_names", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("access_policies", "allowed_tool_names")

    op.drop_column("mcp_request_logs", "status_code")
    op.drop_column("mcp_request_logs", "endpoint_path")
    op.drop_column("mcp_request_logs", "api_service_id")
    op.drop_column("mcp_request_logs", "execution_type")

    op.drop_constraint("chk_mcp_tool_source", "mcp_tools", type_="check")
    op.alter_column("mcp_tools", "server_id", nullable=False)
    op.drop_column("mcp_tools", "api_endpoint_id")
    op.drop_column("mcp_tools", "source_type")
    op.execute("DROP TYPE IF EXISTS mcp_tool_source_type")

    op.drop_index("ix_api_endpoints_api_service_id", table_name="api_endpoints")
    op.drop_table("api_endpoints")
    op.execute("DROP TYPE IF EXISTS rest_http_method")

    op.drop_table("api_services")
    op.execute("DROP TYPE IF EXISTS api_service_status")
    op.execute("DROP TYPE IF EXISTS rest_auth_type")
