import pytest

from app.core.exceptions import BadRequestError
from app.db.models.enums import AgentLifecycleStatus
from app.services.agent_gateway import lifecycle


def test_draft_can_only_move_to_under_review() -> None:
    lifecycle.require_transition(AgentLifecycleStatus.draft, AgentLifecycleStatus.under_review)


def test_draft_cannot_jump_straight_to_active() -> None:
    with pytest.raises(BadRequestError):
        lifecycle.require_transition(AgentLifecycleStatus.draft, AgentLifecycleStatus.active)


def test_under_review_can_move_to_approved_or_rejected() -> None:
    lifecycle.require_transition(AgentLifecycleStatus.under_review, AgentLifecycleStatus.approved)
    lifecycle.require_transition(AgentLifecycleStatus.under_review, AgentLifecycleStatus.rejected)


def test_approved_can_only_move_to_active() -> None:
    lifecycle.require_transition(AgentLifecycleStatus.approved, AgentLifecycleStatus.active)
    with pytest.raises(BadRequestError):
        lifecycle.require_transition(AgentLifecycleStatus.approved, AgentLifecycleStatus.suspended)


def test_active_can_move_to_suspended_or_deprecated_but_not_retired_directly() -> None:
    lifecycle.require_transition(AgentLifecycleStatus.active, AgentLifecycleStatus.suspended)
    lifecycle.require_transition(AgentLifecycleStatus.active, AgentLifecycleStatus.deprecated)
    with pytest.raises(BadRequestError):
        lifecycle.require_transition(AgentLifecycleStatus.active, AgentLifecycleStatus.retired)


def test_suspended_can_move_to_active_or_retired() -> None:
    lifecycle.require_transition(AgentLifecycleStatus.suspended, AgentLifecycleStatus.active)
    lifecycle.require_transition(AgentLifecycleStatus.suspended, AgentLifecycleStatus.retired)


def test_retired_is_terminal() -> None:
    with pytest.raises(BadRequestError):
        lifecycle.require_transition(AgentLifecycleStatus.retired, AgentLifecycleStatus.active)


def test_rejected_can_be_resubmitted() -> None:
    lifecycle.require_transition(AgentLifecycleStatus.rejected, AgentLifecycleStatus.under_review)
