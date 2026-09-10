"""add Identity Provider abstraction layer

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-03

Generalizes `users.keycloak_sub` (Keycloak-only) into `users.external_sub` +
`users.identity_provider`, since a subject id is only unique *within* one
provider -- and adds tenant_identity_config (per-tenant IdP selection) and
access_policies (RBAC/ABAC gate) for the pluggable Identity Provider layer
(app/identity/). See docs/identity-provider-architecture.md.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_IDENTITY_PROVIDER_ENUM = postgresql.ENUM(
    "keycloak", "entra", "auth0", "okta", "aws_identity", "google", "local", name="identity_provider_name"
)


def upgrade() -> None:
    _IDENTITY_PROVIDER_ENUM.create(op.get_bind(), checkfirst=True)

    op.drop_constraint("users_keycloak_sub_key", "users", type_="unique")
    op.alter_column("users", "keycloak_sub", new_column_name="external_sub")
    op.add_column(
        "users",
        sa.Column(
            "identity_provider",
            postgresql.ENUM("keycloak", "entra", "auth0", "okta", "aws_identity", "google", "local", name="identity_provider_name", create_type=False),
            nullable=False,
            server_default="keycloak",
        ),
    )
    op.create_unique_constraint("uq_users_identity_provider_external_sub", "users", ["identity_provider", "external_sub"])

    op.create_table(
        "tenant_identity_config",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.String(), nullable=False, unique=True),
        sa.Column(
            "provider",
            postgresql.ENUM("keycloak", "entra", "auth0", "okta", "aws_identity", "google", "local", name="identity_provider_name", create_type=False),
            nullable=False,
        ),
        sa.Column("issuer", sa.String(), nullable=False, unique=True),
        sa.Column("configuration", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "access_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("allowed_roles", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("allowed_identity_providers", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_access_policies_project_id", "access_policies", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_access_policies_project_id", table_name="access_policies")
    op.drop_table("access_policies")
    op.drop_table("tenant_identity_config")

    op.drop_constraint("uq_users_identity_provider_external_sub", "users", type_="unique")
    op.drop_column("users", "identity_provider")
    op.alter_column("users", "external_sub", new_column_name="keycloak_sub")
    op.create_unique_constraint("users_keycloak_sub_key", "users", ["keycloak_sub"])

    _IDENTITY_PROVIDER_ENUM.drop(op.get_bind(), checkfirst=True)
