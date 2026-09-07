from abc import ABC, abstractmethod
from typing import Any

from app.core.logging import get_logger, log_method
from pydantic import BaseModel


logger = get_logger(__name__)


class GuardrailVerdict(BaseModel):
    allowed: bool
    masked_text: str
    violations: list[dict[str, Any]]


class GuardrailsClient(ABC):
    @abstractmethod
    @log_method(logger)
    async def check_prompt(self, text: str, context: dict[str, Any]) -> GuardrailVerdict: ...

    @abstractmethod
    @log_method(logger)
    async def check_response(self, text: str, context: dict[str, Any]) -> GuardrailVerdict: ...
