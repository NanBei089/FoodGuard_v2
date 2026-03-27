from __future__ import annotations

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.errors import AppBaseException

logger = structlog.get_logger(__name__)

_VALIDATION_FIELD_LABELS = {
    "email": "邮箱",
    "code": "验证码",
    "password": "密码",
    "new_password": "新密码",
    "current_password": "当前密码",
    "page": "页码",
}


def _get_request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _translate_validation_message(field: str, error: dict[str, object]) -> str:
    message = str(error.get("msg", "") or "")
    error_type = str(error.get("type", "") or "")
    context = error.get("ctx")
    if not isinstance(context, dict):
        context = {}

    label = _VALIDATION_FIELD_LABELS.get(field, field or "参数")
    normalized_message = message.lower()

    if error_type == "missing":
        return f"请填写{label}"

    if field == "email":
        return "请输入有效的邮箱地址"

    if field == "code" and error_type in {
        "string_pattern_mismatch",
        "string_too_short",
        "string_too_long",
    }:
        return "验证码必须是 6 位数字"

    if field in {"password", "new_password"}:
        if "uppercase, lowercase, and digit characters" in normalized_message:
            return "密码必须同时包含大写字母、小写字母和数字"
        if error_type == "string_too_short":
            return "密码长度不能少于 8 位"
        if error_type == "string_too_long":
            return "密码长度不能超过 32 位"

    if error_type == "string_too_short":
        min_length = context.get("min_length")
        if isinstance(min_length, int):
            return f"{label}长度不能少于 {min_length} 位"
        return f"{label}长度过短"

    if error_type == "string_too_long":
        max_length = context.get("max_length")
        if isinstance(max_length, int):
            return f"{label}长度不能超过 {max_length} 位"
        return f"{label}长度过长"

    if error_type == "int_parsing":
        return f"{label}必须是整数"

    if error_type == "string_pattern_mismatch":
        return f"{label}格式不正确"

    if message.startswith("Value error, "):
        return message.replace("Value error, ", "", 1)

    return message or "请求参数错误"


def _format_validation_errors(exc: RequestValidationError) -> list[dict[str, str]]:
    formatted: list[dict[str, str]] = []
    for error in exc.errors():
        loc = error.get("loc", ())
        field = str(loc[-1]) if loc else ""
        formatted.append(
            {
                "field": field,
                "message": _translate_validation_message(field, error),
                "type": error.get("type", ""),
            }
        )
    return formatted


def _summarize_validation_errors(errors: list[dict[str, str]]) -> str:
    messages: list[str] = []
    for item in errors:
        message = item.get("message", "").strip()
        if message and message not in messages:
            messages.append(message)

    if not messages:
        return "请求参数错误"
    if len(messages) == 1:
        return messages[0]
    return "；".join(messages[:3])


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
        summary_message = _summarize_validation_errors(formatted_errors)
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
                "message": summary_message,
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
