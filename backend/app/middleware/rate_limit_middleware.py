from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.exceptions import RateLimitError
from app.services.rate_limit_service import RateLimitService

RATE_LIMITED_PATHS = {"/v1/chat/completions", "/v1/embeddings", "/mcp"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path not in RATE_LIMITED_PATHS:
            return await call_next(request)

        principal = getattr(request.state, "principal", None)
        api_key = getattr(principal, "api_key", None) if principal else None
        if api_key is None:
            return await call_next(request)

        try:
            await RateLimitService().check(str(api_key.id))
        except RateLimitError as exc:
            request_id = getattr(request.state, "request_id", None)
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "error": {
                        "code": exc.code,
                        "message": exc.message,
                        "request_id": str(request_id) if request_id else None,
                    }
                },
            )

        return await call_next(request)
