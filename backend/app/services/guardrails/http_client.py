from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import Settings
from app.services.guardrails.base import GuardrailsClient, GuardrailVerdict


class HttpGuardrailsClient(GuardrailsClient):
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.guardrails_base_url
        self._timeout = settings.guardrails_timeout_seconds

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=0.2, max=2),
    )
    async def _check(self, text: str, direction: str, context: dict[str, Any]) -> GuardrailVerdict:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/v1/guardrails/check",
                json={"text": text, "direction": direction, "context": context},
            )
        response.raise_for_status()
        return GuardrailVerdict.model_validate(response.json())

    async def check_prompt(self, text: str, context: dict[str, Any]) -> GuardrailVerdict:
        return await self._check(text, "prompt", context)

    async def check_response(self, text: str, context: dict[str, Any]) -> GuardrailVerdict:
        return await self._check(text, "response", context)
