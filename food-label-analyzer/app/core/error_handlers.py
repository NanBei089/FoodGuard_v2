from __future__ import annotations

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.errors import AppBaseException


logger = structlog.get_logger(__name__)


def _get_request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _format_validation_errors(exc: RequestValidationError) -> list[dict[str, str]]:
    formatted: list[dict[str, str]] = []
    for error in exc.errors():
        loc = error.get("loc", ())
        field = str(loc[-1]) if loc else ""
        formatted.append(
            {
                "field": field,
                "message": error.get("msg", ""),
                "type": error.get("type", ""),
            }
        )
    return formatted


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppBaseException)
    async def app_base_exception_handler(
        request: Request,
        exc: AppBaseException,
    ) -> JSONResponse:
        logger.warning(
            "app_exception_handled",
            path=request.url.path,
            method=request.method,
            request_id=_get_request_id(request),
            status_code=exc.status_code,
            error_code=exc.error_code,
            message=exc.message,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.error_code,
                "message": exc.message,
                "data": exc.detail,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        formatted_errors = _format_validation_errors(exc)
        logger.warning(
            "request_validation_failed",
            path=request.url.path,
            method=request.method,
            request_id=_get_request_id(request),
            errors=formatted_errors,
        )
        return JSONResponse(
            status_code=422,
            content={
                "code": 4220,
                "message": "请求参数错误",
                "data": {"errors": formatted_errors},
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            request_id=_get_request_id(request),
            exception_type=exc.__class__.__name__,
            exception_message=str(exc),
            exc_info=exc,
        )

        data = None
        if get_settings().APP_DEBUG:
            data = {
                "exception_type": exc.__class__.__name__,
                "message": str(exc),
            }

        return JSONResponse(
            status_code=500,
            content={
                "code": 5001,
                "message": "服务器内部错误",
                "data": data,
            },
        )


__all__ = ["register_exception_handlers"]
