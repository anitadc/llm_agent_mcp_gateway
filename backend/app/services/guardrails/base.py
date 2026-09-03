from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class GuardrailVerdict(BaseModel):
    allowed: bool
    masked_text: str
    violations: list[dict[str, Any]]


class GuardrailsClient(ABC):
    @abstractmethod
    @log_method(get_logger(__name__))
    async def check_prompt(self, text: str, context: dict[str, Any]) -> GuardrailVerdict: ...

    @abstractmethod
    @log_method(get_logger(__name__))
    async def check_response(self, text: str, context: dict[str, Any]) -> GuardrailVerdict: ...
