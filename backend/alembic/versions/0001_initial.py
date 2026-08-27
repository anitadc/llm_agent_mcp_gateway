"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-24

Hand-authored to match TDD.md §3.2 exactly (no live DB was available to
autogenerate against). Any future schema change should be its own
incremental migration, never a hand-edit of this file.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

user_role = postgresql.ENUM("admin", "team_lead", "developer", "viewer", name="user_role")
provider_name = postgresql.ENUM("openai", "anthropic", "bedrock", name="provider_name")
routing_strategy = postgresql.ENUM("priority", "cost", "latency", name="routing_strategy")
request_status = postgresql.ENUM("success", "error", "blocked", "rate_limited", name="request_status")
budget_period = postgresql.ENUM("daily", "monthly", name="budget_period")
guardrail_direction = postgresql.ENUM("prompt", "response", name="guardrail_direction")
model_capability = postgresql.ENUM("chat", "embedding", name="model_capability")

ALL_ENUMS = [
    user_role,
    provider_name,
    routing_strategy,
    request_status,
    budget_period,
    guardrail_direction,
    model_capability,
]


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in ALL_ENUMS:
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("organization_id", "name"),
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("keycloak_sub", sa.Text(), nullable=True, unique=True),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "role",
            postgresql.ENUM("admin", "team_lead", "developer", "viewer", name="user_role", create_type=False),
            nullable=False,
            server_default="developer",
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "project_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_project_users_project", "project_users", ["project_id"])
    op.create_index("idx_project_users_user", "project_users", ["user_id"])
    op.create_index(
        "idx_project_users_one_active",
        "project_users",
        ["project_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("end_date IS NULL"),
    )

    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("hashed_key", sa.Text(), nullable=False, unique=True),
        sa.Column("prefix", sa.String(12), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("scopes", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_api_keys_project", "api_keys", ["project_id"])

    op.create_table(
        "provider_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "provider",
            postgresql.ENUM("openai", "anthropic", "bedrock", name="provider_name", create_type=False),
            nullable=False,
        ),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("credential_ref", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("provider", "display_name"),
    )

    op.create_table(
        "routing_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("model_alias", sa.Text(), nullable=False),
        sa.Column(
            "project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("user_id", sa.Text(), nullable=True),
        sa.Column(
            "capability",
            postgresql.ENUM("chat", "embedding", name="model_capability", create_type=False),
            nullable=False,
            server_default="chat",
        ),
        sa.Column(
            "strategy",
            postgresql.ENUM("priority", "cost", "latency", name="routing_strategy", create_type=False),
            nullable=False,
            server_default="priority",
        ),
        sa.Column("targets", postgresql.JSONB(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_routing_rules_alias", "routing_rules", ["model_alias", "project_id", "capability"])
    op.create_index("idx_routing_rules_user", "routing_rules", ["model_alias", "project_id", "user_id"])

    op.create_table(
        "request_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column(
            "api_key_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model_alias", sa.Text(), nullable=False),
        sa.Column(
            "capability",
            postgresql.ENUM("chat", "embedding", name="model_capability", create_type=False),
            nullable=False,
            server_default="chat",
        ),
        sa.Column("resolved_provider", sa.Text(), nullable=True),
        sa.Column("resolved_model", sa.Text(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM("success", "error", "blocked", "rate_limited", name="request_status", create_type=False),
            nullable=False,
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_hit", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_request_logs_project_created", "request_logs", ["project_id", sa.text("created_at DESC")])
    op.create_index(
        "idx_request_logs_organization_created", "request_logs", ["organization_id", sa.text("created_at DESC")]
    )
    op.create_index("idx_request_logs_user", "request_logs", ["user_id"])
    op.create_index("idx_request_logs_status", "request_logs", ["status"])
    op.create_index("idx_request_logs_capability", "request_logs", ["capability"])

    op.create_table(
        "cost_ledger",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "request_log_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("request_logs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_cost_ledger_organization_created", "cost_ledger", ["organization_id", sa.text("created_at DESC")])
    op.create_index("idx_cost_ledger_project_created", "cost_ledger", ["project_id", sa.text("created_at DESC")])
    op.create_index("idx_cost_ledger_user_created", "cost_ledger", ["user_id", sa.text("created_at DESC")])

    op.create_table(
        "budgets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column(
            "period",
            postgresql.ENUM("daily", "monthly", name="budget_period", create_type=False),
            nullable=False,
            server_default="monthly",
        ),
        sa.Column("limit_usd", sa.Numeric(12, 2), nullable=False),
        sa.Column("alert_threshold_pct", sa.Integer(), nullable=False, server_default="80"),
        sa.CheckConstraint(
            "organization_id IS NOT NULL OR project_id IS NOT NULL OR user_id IS NOT NULL",
            name="chk_budget_scope",
        ),
    )

    op.create_table(
        "guardrail_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "request_log_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("request_logs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "direction",
            postgresql.ENUM("prompt", "response", name="guardrail_direction", create_type=False),
            nullable=False,
        ),
        sa.Column("allowed", sa.Boolean(), nullable=False),
        sa.Column("violations", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_guardrail_results_request", "guardrail_results", ["request_log_id"])


def downgrade() -> None:
    op.drop_table("guardrail_results")
    op.drop_table("budgets")
    op.drop_table("cost_ledger")
    op.drop_table("request_logs")
    op.drop_table("routing_rules")
    op.drop_table("provider_configs")
    op.drop_table("api_keys")
    op.drop_table("project_users")
    op.drop_table("users")
    op.drop_table("projects")
    op.drop_table("organizations")

    bind = op.get_bind()
    for enum_type in reversed(ALL_ENUMS):
        enum_type.drop(bind, checkfirst=True)
