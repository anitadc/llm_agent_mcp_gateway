class GatewayException(Exception):
    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class AuthError(GatewayException):
    status_code = 401
    code = "unauthorized"


class ForbiddenError(GatewayException):
    status_code = 403
    code = "forbidden"


class RateLimitError(GatewayException):
    status_code = 429
    code = "rate_limited"


class GuardrailBlockedError(GatewayException):
    status_code = 422
    code = "guardrail_blocked"


class ProviderError(GatewayException):
    status_code = 502
    code = "provider_error"


class NotFoundError(GatewayException):
    status_code = 404
    code = "not_found"


class BadRequestError(GatewayException):
    status_code = 400
    code = "bad_request"
