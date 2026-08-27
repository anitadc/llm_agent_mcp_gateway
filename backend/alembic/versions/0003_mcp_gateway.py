"""add MCP gateway tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-01

Adds the MCP Gateway's own tables: mcp_servers (the MCP Server Registry --
transport/auth config plus operator status and observed health/sync state),
mcp_tools (the central tool_name -> server registry built by discovery),
mcp_sessions (client_session_id -> per-server session id mapping), and
mcp_request_logs (observability, the MCP analogue of request_logs).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mcp_servers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("base_url", sa.String(), nullable=False),
        sa.Column(
            "transport_type",
            postgresql.ENUM("http", name="mcp_transport_type"),
            nullable=False,
            server_default="http",
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("auth_config", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "status",
            postgresql.ENUM("active", "inactive", name="mcp_server_status"),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "health_status",
            postgresql.ENUM("unknown", "healthy", "unhealthy", name="mcp_health_status"),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=True),
        sa.Column("protocol_version", sa.String(), nullable=True),
        sa.Column(
            "last_sync_status",
            postgresql.ENUM("pending", "success", "error", name="mcp_sync_status"),
            nullable=True,
        ),
        sa.Column("last_sync_error", sa.Text(), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_latency_ms", sa.Integer(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "mcp_tools",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "server_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mcp_servers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("input_schema", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_mcp_tools_server_id", "mcp_tools", ["server_id"])

    op.create_table(
        "mcp_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("client_session_id", sa.String(), nullable=False, unique=True),
        sa.Column(
            "project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "api_key_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("server_sessions", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "mcp_request_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column(
            "api_key_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("client_session_id", sa.String(), nullable=True),
        sa.Column("method", sa.String(), nullable=False),
        sa.Column("tool_name", sa.String(), nullable=True),
        sa.Column(
            "server_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mcp_servers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status", postgresql.ENUM("success", "error", "blocked", "rate_limited", name="request_status", create_type=False), nullable=False
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_mcp_request_logs_tool_name", "mcp_request_logs", ["tool_name"])
    op.create_index("ix_mcp_request_logs_created_at", "mcp_request_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_mcp_request_logs_created_at", table_name="mcp_request_logs")
    op.drop_index("ix_mcp_request_logs_tool_name", table_name="mcp_request_logs")
    op.drop_table("mcp_request_logs")
    op.drop_table("mcp_sessions")
    op.drop_index("ix_mcp_tools_server_id", table_name="mcp_tools")
    op.drop_table("mcp_tools")
    op.drop_table("mcp_servers")
    op.execute("DROP TYPE IF EXISTS mcp_sync_status")
    op.execute("DROP TYPE IF EXISTS mcp_health_status")
    op.execute("DROP TYPE IF EXISTS mcp_server_status")
    op.execute("DROP TYPE IF EXISTS mcp_transport_type")
