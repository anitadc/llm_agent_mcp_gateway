"""add secret_audit_log table

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-02

Adds the audit trail for the Secret Provider layer (app/secrets/). Deliberately
has no column that could ever hold a secret value -- see docs/secret-management.md.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "secret_audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.String(), nullable=True),
        sa.Column(
            "operation",
            postgresql.ENUM("get", "set", "delete", "rotate", name="secret_operation"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("secret_name", sa.String(), nullable=False),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "status", postgresql.ENUM("success", "error", name="secret_audit_status"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_secret_audit_log_created_at", "secret_audit_log", ["created_at"])
    op.create_index("ix_secret_audit_log_secret_name", "secret_audit_log", ["secret_name"])


def downgrade() -> None:
    op.drop_index("ix_secret_audit_log_secret_name", table_name="secret_audit_log")
    op.drop_index("ix_secret_audit_log_created_at", table_name="secret_audit_log")
    op.drop_table("secret_audit_log")
    op.execute("DROP TYPE IF EXISTS secret_audit_status")
    op.execute("DROP TYPE IF EXISTS secret_operation")
