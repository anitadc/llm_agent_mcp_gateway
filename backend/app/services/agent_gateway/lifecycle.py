"""Agent Gateway lifecycle state machine (MVP).

The full spec's lifecycle is
`draft -> submitted -> validating -> under_review -> approved -> published ->
active -> {suspended, deprecated} -> retired` (plus `rejected` from
validation/review). This MVP pass treats `submitted`/`validating`/`published`
as instantaneous, not independently persisted states: card validation runs
synchronously inside `submit_for_approval` (nothing async to be "validating"
against yet), and `publish` moves an agent straight from `approved` to
`active` (there is currently no separate deployment/activation step after
publication). Those three enum values are reserved for when that becomes real,
not removed from the schema -- but no code path assigns them today.
"""

from app.core.exceptions import BadRequestError
from app.core.logging import get_logger, log_method
from app.db.models.enums import AgentLifecycleStatus

logger = get_logger(__name__)

ALLOWED_TRANSITIONS: dict[AgentLifecycleStatus, set[AgentLifecycleStatus]] = {
    AgentLifecycleStatus.draft: {AgentLifecycleStatus.under_review},
    AgentLifecycleStatus.rejected: {AgentLifecycleStatus.under_review},
    AgentLifecycleStatus.under_review: {AgentLifecycleStatus.approved, AgentLifecycleStatus.rejected},
    AgentLifecycleStatus.approved: {AgentLifecycleStatus.active},
    AgentLifecycleStatus.active: {AgentLifecycleStatus.suspended, AgentLifecycleStatus.deprecated},
    AgentLifecycleStatus.suspended: {AgentLifecycleStatus.active, AgentLifecycleStatus.retired},
    AgentLifecycleStatus.deprecated: {AgentLifecycleStatus.retired},
}


@log_method(logger)
def require_transition(current: AgentLifecycleStatus, target: AgentLifecycleStatus) -> None:
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        logger.warning("agent_lifecycle_transition_denied", current_status=current.value, target_status=target.value)
        raise BadRequestError(f"Cannot transition agent from '{current.value}' to '{target.value}'")
