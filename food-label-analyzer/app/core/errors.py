from __future__ import annotations

from typing import Any

"""业务异常定义，统一承载 HTTP 状态码、业务错误码和前端可见消息。"""


class AppBaseException(Exception):
    """应用异常基类。

    Params:
        message: 覆盖默认错误消息。
        detail: 额外错误详情，通常用于前端字段级处理。
        status_code: 覆盖默认 HTTP 状态码。
        error_code: 覆盖默认业务错误码。
    """

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
    """认证失败类异常。"""

    status_code = 401
    error_code = 4010
    message = "认证失败"


class InvalidCredentialsError(AuthException):
    """邮箱或密码不匹配。"""

    error_code = 4010
    message = "邮箱或密码错误"


class EmailNotVerifiedError(AppBaseException):
    """邮箱尚未完成验证。"""

    status_code = 403
    error_code = 4011
    message = "邮箱尚未完成验证"


class PasswordResetTokenInvalidError(AppBaseException):
    """密码重置令牌无效或过期。"""

    status_code = 400
    error_code = 4012
    message = "密码重置链接无效或已过期"


class TokenExpiredError(AuthException):
    """JWT 已过期。"""

    error_code = 4013
    message = "令牌已过期"


class TokenInvalidError(AuthException):
    """JWT 无效或类型不符合当前接口要求。"""

    error_code = 4014
    message = "令牌无效"


class ValidationException(AppBaseException):
    """业务参数校验失败。"""

    status_code = 422
    error_code = 4220
    message = "请求参数错误"


class InvalidVerifyCodeError(AppBaseException):
    """验证码无效、过期或已使用。"""

    status_code = 400
    error_code = 4003
    message = "验证码无效或已过期"


class PasswordTooWeakError(AppBaseException):
    """密码强度不满足安全策略。"""

    status_code = 400
    error_code = 4004
    message = "密码强度不足"


class FileTooLargeError(AppBaseException):
    """上传文件超过配置限制。"""

    status_code = 400
    error_code = 4022
    message = "上传文件过大"


class InvalidFileTypeError(AppBaseException):
    """上传文件类型或内容不符合要求。"""

    status_code = 400
    error_code = 4021
    message = "上传文件类型不支持"


class CooldownError(AppBaseException):
    """请求触发冷却限制。"""

    status_code = 429
    error_code = 4002
    message = "请求过于频繁，请稍后再试"

    def __init__(
        self,
        retry_after_seconds: int,
        message: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        """构造带 retry_after_seconds 的冷却错误。"""
        payload = {"retry_after_seconds": retry_after_seconds}
        if detail:
            payload.update(detail)
        super().__init__(message=message, detail=payload)


class ResourceException(AppBaseException):
    """资源不存在类异常。"""

    status_code = 404
    error_code = 4040
    message = "请求的资源不存在"


class UserNotFoundError(ResourceException):
    """用户不存在。"""

    error_code = 4040
    message = "用户不存在"


class TaskNotFoundError(ResourceException):
    """分析任务不存在。"""

    error_code = 4041
    message = "分析任务不存在"


class ReportNotFoundError(ResourceException):
    """分析报告不存在。"""

    error_code = 4042
    message = "报告不存在"


class EmailAlreadyExistsError(AppBaseException):
    """注册邮箱已经存在。"""

    status_code = 409
    error_code = 4001
    message = "邮箱已注册"


class TooManyConcurrentTasksError(AppBaseException):
    """用户当前进行中的分析任务过多。"""

    status_code = 429
    error_code = 4024
    message = "当前进行中的任务过多，请稍后再试"


class ExternalServiceException(AppBaseException):
    """外部依赖不可用类异常。"""

    status_code = 503
    error_code = 5000
    message = "外部服务暂时不可用"


class OCRServiceError(ExternalServiceException):
    """OCR 服务不可用或识别失败。"""

    message = "OCR 服务暂时不可用"


class LLMServiceError(ExternalServiceException):
    """LLM 服务不可用或输出异常。"""

    message = "大模型服务暂时不可用"


class StorageServiceError(ExternalServiceException):
    """对象存储服务不可用。"""

    message = "存储服务暂时不可用"


class EmbeddingServiceError(ExternalServiceException):
    """向量检索或 embedding 服务不可用。"""

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
