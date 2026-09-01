import uuid

from fastapi import APIRouter, Depends

from app.api.deps import get_routing_rule_repo, require_roles
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.db.models.enums import UserRole
from app.db.models.routing_rule import RoutingRule
from app.db.models.user import User
from app.repositories.routing_rule_repo import RoutingRuleRepo
from app.schemas.routing_rule import RoutingRuleCreate, RoutingRuleOut, RoutingRuleUpdate

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/routing-rules", tags=["routing_rules"])


@router.get("", response_model=list[RoutingRuleOut])
async def list_routing_rules(
    user: User = Depends(require_roles(UserRole.admin)), repo: RoutingRuleRepo = Depends(get_routing_rule_repo)
) -> list[RoutingRuleOut]:
    rules = await repo.list_all()
    logger.info("listing routing rules", user_id=user.id, count=len(rules))
    return [RoutingRuleOut.model_validate(r) for r in rules]


@router.post("", response_model=RoutingRuleOut, status_code=201)
async def create_routing_rule(
    body: RoutingRuleCreate,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: RoutingRuleRepo = Depends(get_routing_rule_repo),
) -> RoutingRuleOut:
    logger.info("creating routing rule", user_id=user.id, model_alias=body.model_alias, capability=body.capability.value, priority=body.priority)
    rule = await repo.add(
        RoutingRule(
            model_alias=body.model_alias,
            project_id=body.project_id,
            user_id=body.user_id,
            capability=body.capability,
            strategy=body.strategy,
            targets=[t.model_dump(exclude_none=True) for t in body.targets],
            priority=body.priority,
            is_active=body.is_active,
        )
    )
    logger.info("routing_rule_created", rule_id=str(rule.id), model_alias=rule.model_alias, strategy=rule.strategy.value)
    return RoutingRuleOut.model_validate(rule)


@router.patch("/{rule_id}", response_model=RoutingRuleOut)
async def update_routing_rule(
    rule_id: uuid.UUID,
    body: RoutingRuleUpdate,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: RoutingRuleRepo = Depends(get_routing_rule_repo),
) -> RoutingRuleOut:
    logger.info("updating routing rule", user_id=user.id, rule_id=str(rule_id), fields=list(body.model_dump(exclude_none=True).keys()))
    rule = await repo.get(rule_id)
    if rule is None:
        raise NotFoundError("Routing rule not found")
    if body.strategy is not None:
        rule.strategy = body.strategy
    if body.targets is not None:
        rule.targets = [t.model_dump(exclude_none=True) for t in body.targets]
    if body.priority is not None:
        rule.priority = body.priority
    if body.is_active is not None:
        rule.is_active = body.is_active
    await repo.db.flush()
    await repo.db.refresh(rule)
    logger.info("routing_rule_updated", rule_id=str(rule_id))
    return RoutingRuleOut.model_validate(rule)
