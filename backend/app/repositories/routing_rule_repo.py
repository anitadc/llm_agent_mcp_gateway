import uuid

from sqlalchemy import or_, select

from app.db.models.enums import ModelCapability
from app.db.models.routing_rule import RoutingRule
from app.repositories.base import BaseRepository


class RoutingRuleRepo(BaseRepository[RoutingRule]):
    model = RoutingRule

    async def find_best_match(
        self,
        model_alias: str,
        capability: ModelCapability,
        project_id: uuid.UUID,
        user_id: str | None = None,
    ) -> RoutingRule | None:
        """Implements the three-tier specificity resolution from TDD.md §3.2.5:
        project+user match beats project-only match beats global; ties broken by priority.
        """
        user_filter = (
            or_(RoutingRule.user_id.is_(None), RoutingRule.user_id == user_id)
            if user_id
            else RoutingRule.user_id.is_(None)
        )
        stmt = select(RoutingRule).where(
            RoutingRule.model_alias == model_alias,
            RoutingRule.capability == capability,
            RoutingRule.is_active.is_(True),
            or_(RoutingRule.project_id.is_(None), RoutingRule.project_id == project_id),
            user_filter,
        )
        result = await self.db.execute(stmt)
        candidates = list(result.scalars().all())
        if not candidates:
            return None

        def specificity(rule: RoutingRule) -> int:
            return (1 if rule.project_id else 0) + (1 if rule.user_id else 0)

        candidates.sort(key=lambda rule: (specificity(rule), rule.priority), reverse=True)
        return candidates[0]

    async def list_all(self) -> list[RoutingRule]:
        result = await self.db.execute(select(RoutingRule))
        return list(result.scalars().all())
