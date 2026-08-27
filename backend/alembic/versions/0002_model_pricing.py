"""add model_pricing table

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-25

Moves per-model USD pricing out of a hardcoded Python dict
(services/cost_service.py) into the database, so it's admin-editable
via the API/UI without a code change + redeploy. Seeds the exact
values that were previously hardcoded, so cost calculation and
cost-based routing behave identically immediately after this migration.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "model_pricing",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "provider",
            postgresql.ENUM("openai", "anthropic", "bedrock", name="provider_name", create_type=False),
            nullable=False,
        ),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_per_1k", sa.Numeric(12, 6), nullable=False),
        sa.Column("completion_per_1k", sa.Numeric(12, 6), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("provider", "model"),
    )

    model_pricing = sa.table(
        "model_pricing",
        sa.column(
            "provider", postgresql.ENUM("openai", "anthropic", "bedrock", name="provider_name", create_type=False)
        ),
        sa.column("model", sa.String),
        sa.column("prompt_per_1k", sa.Numeric),
        sa.column("completion_per_1k", sa.Numeric),
    )
    op.bulk_insert(
        model_pricing,
        [
            {"provider": "openai", "model": "gpt-4o", "prompt_per_1k": "0.0050", "completion_per_1k": "0.0150"},
            {"provider": "openai", "model": "gpt-4o-mini", "prompt_per_1k": "0.00015", "completion_per_1k": "0.0006"},
            {"provider": "openai", "model": "text-embedding-3-small", "prompt_per_1k": "0.00002", "completion_per_1k": None},
            {
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20241022",
                "prompt_per_1k": "0.0030",
                "completion_per_1k": "0.0150",
            },
            {
                "provider": "anthropic",
                "model": "claude-3-5-haiku-20241022",
                "prompt_per_1k": "0.0008",
                "completion_per_1k": "0.0040",
            },
            {
                "provider": "bedrock",
                "model": "anthropic.claude-3-sonnet-20240229-v1:0",
                "prompt_per_1k": "0.0030",
                "completion_per_1k": "0.0150",
            },
            {
                "provider": "bedrock",
                "model": "anthropic.claude-3-haiku-20240307-v1:0",
                "prompt_per_1k": "0.00025",
                "completion_per_1k": "0.00125",
            },
            {
                "provider": "bedrock",
                "model": "amazon.titan-embed-text-v2:0",
                "prompt_per_1k": "0.00002",
                "completion_per_1k": None,
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("model_pricing")
