"""add Agent Gateway (MVP: registry, approval workflow, governed invocation)

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-20

Adds the Agent Gateway's MVP tables per docs/agent-gateway.md:

- agents: the Agent Registry -- one row per registered agent, its (simplified,
  not A2A-schema-validated) Agent Card, and governance state (lifecycle status,
  risk class, trust level).
- agent_approval_tasks: one review-stage instance per agent registration,
  stages driven by configuration (Settings.agent_approval_stages), not hard-coded.
- agent_invocations: observability/audit record for every governed invocation,
  the Agent Gateway analogue of mcp_request_logs.
- access_policies gains allowed_agent_keys, extending the existing RBAC/ABAC
  gate (PolicyEngine) to Agent Gateway invocations the same way
  allowed_tool_names already covers MCP/REST tool calls.

Full A2A protocol compliance, the LangGraph same-process boundary, and the
Python SDK are explicitly Future Capability -- see docs/agent-gateway.md.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("agent_key", sa.String(), nullable=False, unique=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_team", sa.String(), nullable=True),
        sa.Column("domain", sa.String(), nullable=True),
        sa.Column("version", sa.String(), nullable=False, server_default="1.0.0"),
        sa.Column("capabilities", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column(
            "risk_class",
            postgresql.ENUM("low", "medium", "high", name="agent_risk_class"),
            nullable=False,
            server_default="low",
        ),
        sa.Column(
            "trust_level",
            postgresql.ENUM(
                "t0_unknown",
                "t1_registered_internal",
                "t2_enterprise_trusted",
                "t3_privileged",
                "t4_approved_external_partner",
                "t5_public_untrusted",
                name="agent_trust_level",
            ),
            nullable=False,
            server_default="t1_registered_internal",
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "draft",
                "submitted",
                "validating",
                "under_review",
                "approved",
                "published",
                "active",
                "suspended",
                "deprecated",
                "retired",
                "rejected",
                name="agent_lifecycle_status",
            ),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("endpoint_url", sa.String(), nullable=True),
        sa.Column("auth_config", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("card", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "submitted_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_agents_status", "agents", ["status"])

    op.create_table(
        "agent_approval_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "agent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "stage",
            postgresql.ENUM(
                "security", "technical", "business", "data_governance", "production", name="agent_approval_stage"
            ),
            nullable=False,
        ),
        sa.Column(
            "decision",
            postgresql.ENUM("pending", "approved", "rejected", name="agent_approval_decision"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "approver_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_agent_approval_tasks_agent_id", "agent_approval_tasks", ["agent_id"])

    op.create_table(
        "agent_invocations",
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
        sa.Column("capability", sa.String(), nullable=False),
        sa.Column("operation", sa.String(), nullable=True),
        sa.Column(
            "agent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("authorization_decision", sa.String(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM("success", "error", "blocked", "rate_limited", name="request_status", create_type=False),
            nullable=False,
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_agent_invocations_capability", "agent_invocations", ["capability"])
    op.create_index("ix_agent_invocations_created_at", "agent_invocations", ["created_at"])

    op.add_column(
        "access_policies",
        sa.Column("allowed_agent_keys", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("access_policies", "allowed_agent_keys")

    op.drop_index("ix_agent_invocations_created_at", table_name="agent_invocations")
    op.drop_index("ix_agent_invocations_capability", table_name="agent_invocations")
    op.drop_table("agent_invocations")

    op.drop_index("ix_agent_approval_tasks_agent_id", table_name="agent_approval_tasks")
    op.drop_table("agent_approval_tasks")
    op.execute("DROP TYPE IF EXISTS agent_approval_decision")
    op.execute("DROP TYPE IF EXISTS agent_approval_stage")

    op.drop_index("ix_agents_status", table_name="agents")
    op.drop_table("agents")
    op.execute("DROP TYPE IF EXISTS agent_lifecycle_status")
    op.execute("DROP TYPE IF EXISTS agent_trust_level")
    op.execute("DROP TYPE IF EXISTS agent_risk_class")
