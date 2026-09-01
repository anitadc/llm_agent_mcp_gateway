from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import Settings
from app.core.exceptions import ProviderError
from app.core.logging import get_logger
from app.services.guardrails.base import GuardrailsClient, GuardrailVerdict

logger = get_logger(__name__)


class HttpGuardrailsClient(GuardrailsClient):
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.guardrails_base_url
        self._timeout = settings.guardrails_timeout_seconds

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=0.2, max=2),
        reraise=True,
    )
    async def _post_check(self, text: str, direction: str, context: dict[str, Any]) -> GuardrailVerdict:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/v1/guardrails/check",
                json={"text": text, "direction": direction, "context": context},
            )
        response.raise_for_status()
        return GuardrailVerdict.model_validate(response.json())

    async def _check(self, text: str, direction: str, context: dict[str, Any]) -> GuardrailVerdict:
        url = f"{self._base_url}/v1/guardrails/check"
        try:
            response = await self._post_check(text, direction, context)
        except httpx.HTTPError as exc:
            logger.exception("guardrails_request_failed", url=url, direction=direction)
            raise ProviderError(f"Guardrails service request failed: {exc}") from exc
        verdict = GuardrailVerdict.model_validate(response.json())
        logger.info(
            "guardrail_check_completed",
            direction=direction,
            allowed=verdict.allowed,
            violation_count=len(verdict.violations),
        )
        return verdict

    async def check_prompt(self, text: str, context: dict[str, Any]) -> GuardrailVerdict:
        return await self._check(text, "prompt", context)

    async def check_response(self, text: str, context: dict[str, Any]) -> GuardrailVerdict:
        return await self._check(text, "response", context)
