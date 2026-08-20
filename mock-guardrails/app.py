import re
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Mock Guardrails Service")

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b")


class GuardrailsCheckRequest(BaseModel):
    text: str
    direction: Literal["prompt", "response"]
    context: dict = {}


class Violation(BaseModel):
    type: str
    detail: str


class GuardrailsCheckResponse(BaseModel):
    allowed: bool
    masked_text: str
    violations: list[Violation]


@app.post("/v1/guardrails/check", response_model=GuardrailsCheckResponse)
async def check(body: GuardrailsCheckRequest) -> GuardrailsCheckResponse:
    """Trivial regex-based PII masking (emails, phone numbers), per TDD.md §5.2 --
    a stand-in until the real guardrails service's contract is confirmed. Never
    blocks (allowed is always true); it exists to exercise the full pipeline
    (masking + violation reporting), not to enforce real policy."""
    violations: list[Violation] = []
    masked = body.text

    if EMAIL_RE.search(masked):
        violations.append(Violation(type="pii_detected", detail="email address"))
        masked = EMAIL_RE.sub("[REDACTED_EMAIL]", masked)

    if PHONE_RE.search(masked):
        violations.append(Violation(type="pii_detected", detail="phone number"))
        masked = PHONE_RE.sub("[REDACTED_PHONE]", masked)

    return GuardrailsCheckResponse(allowed=True, masked_text=masked, violations=violations)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
