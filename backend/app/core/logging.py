import inspect
import logging
import sys
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

import structlog

request_id_var = structlog.contextvars.bind_contextvars

T = TypeVar("T")


def configure_logging(log_level: str) -> None:
    logging.basicConfig(stream=sys.stdout, level=log_level, format="%(message)s", force=True)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            structlog.processors.ExceptionRenderer(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(log_level)),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


def log_method(logger_obj: Any | None = None) -> Callable[[Callable[..., T]], Callable[..., T]]:
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        target_logger = logger_obj or get_logger(func.__module__)

        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> T:
                target_logger.info("method_start", method=func.__qualname__)
                try:
                    result = await func(*args, **kwargs)
                except Exception:
                    target_logger.exception("method_failed", method=func.__qualname__)
                    raise
                target_logger.info("method_end", method=func.__qualname__)
                return result

            return async_wrapper

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> T:
            target_logger.info("method_start", method=func.__qualname__)
            try:
                result = func(*args, **kwargs)
            except Exception:
                target_logger.exception("method_failed", method=func.__qualname__)
                raise
            target_logger.info("method_end", method=func.__qualname__)
            return result

        return sync_wrapper

    return decorator
