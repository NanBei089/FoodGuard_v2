from __future__ import annotations

from typing import Any


class AppBaseException(Exception):
    status_code = 500
    error_code = 5000
    message = "服务异常"

    def __init__(
        self,
        message: str | None = None,
        detail: dict[str, Any] | None = None,
        *,
        status_code: int | None = None,
        error_code: int | None = None,
    ) -> None:
        self.status_code = (
            status_code if status_code is not None else type(self).status_code
        )
        self.error_code = (
            error_code if error_code is not None else type(self).error_code
        )
        self.message = message if message is not None else type(self).message
        self.detail = detail
        super().__init__(self.message)


class AuthException(AppBaseException):
    status_code = 401
    error_code = 4010
    message = "认证失败"


class InvalidCredentialsError(AuthException):
    error_code = 4010
    message = "邮箱或密码错误"


class EmailNotVerifiedError(AppBaseException):
    status_code = 403
    error_code = 4011
    message = "邮箱尚未完成验证"


class PasswordResetTokenInvalidError(AppBaseException):
    status_code = 400
    error_code = 4012
    message = "密码重置链接无效或已过期"


class TokenExpiredError(AuthException):
    error_code = 4013
    message = "令牌已过期"


class TokenInvalidError(AuthException):
    error_code = 4014
    message = "令牌无效"


class ValidationException(AppBaseException):
    status_code = 422
    error_code = 4220
    message = "请求参数错误"


class InvalidVerifyCodeError(AppBaseException):
    status_code = 400
    error_code = 4003
    message = "验证码无效或已过期"


class PasswordTooWeakError(AppBaseException):
    status_code = 400
    error_code = 4004
    message = "密码强度不足"


class FileTooLargeError(AppBaseException):
    status_code = 400
    error_code = 4022
    message = "上传文件过大"


class InvalidFileTypeError(AppBaseException):
    status_code = 400
    error_code = 4021
    message = "上传文件类型不支持"


class CooldownError(AppBaseException):
    status_code = 429
    error_code = 4002
    message = "请求过于频繁，请稍后再试"

    def __init__(
        self,
        retry_after_seconds: int,
        message: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        payload = {"retry_after_seconds": retry_after_seconds}
        if detail:
            payload.update(detail)
        super().__init__(message=message, detail=payload)


class ResourceException(AppBaseException):
    status_code = 404
    error_code = 4040
    message = "请求的资源不存在"


class UserNotFoundError(ResourceException):
    error_code = 4040
    message = "用户不存在"


class TaskNotFoundError(ResourceException):
    error_code = 4041
    message = "分析任务不存在"


class ReportNotFoundError(ResourceException):
    error_code = 4042
    message = "报告不存在"


class EmailAlreadyExistsError(AppBaseException):
    status_code = 409
    error_code = 4001
    message = "邮箱已注册"


class TooManyConcurrentTasksError(AppBaseException):
    status_code = 429
    error_code = 4024
    message = "当前进行中的任务过多，请稍后再试"


class ExternalServiceException(AppBaseException):
    status_code = 503
    error_code = 5000
    message = "外部服务暂时不可用"


class OCRServiceError(ExternalServiceException):
    message = "OCR 服务暂时不可用"


class LLMServiceError(ExternalServiceException):
    message = "大模型服务暂时不可用"


class StorageServiceError(ExternalServiceException):
    message = "存储服务暂时不可用"


class EmbeddingServiceError(ExternalServiceException):
    message = "知识检索服务暂时不可用"


__all__ = [
    "AppBaseException",
    "AuthException",
    "CooldownError",
    "EmbeddingServiceError",
    "EmailAlreadyExistsError",
    "EmailNotVerifiedError",
    "ExternalServiceException",
    "FileTooLargeError",
    "InvalidCredentialsError",
    "InvalidFileTypeError",
    "InvalidVerifyCodeError",
    "LLMServiceError",
    "OCRServiceError",
    "PasswordResetTokenInvalidError",
    "PasswordTooWeakError",
    "ReportNotFoundError",
    "ResourceException",
    "StorageServiceError",
    "TaskNotFoundError",
    "TokenExpiredError",
    "TokenInvalidError",
    "TooManyConcurrentTasksError",
    "UserNotFoundError",
    "ValidationException",
]
