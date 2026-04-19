from __future__ import annotations

import enum

"""数据库与业务层共享的枚举值。"""


class TaskStatus(str, enum.Enum):
    """分析任务内部状态。"""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class VerificationType(str, enum.Enum):
    """邮箱验证码用途。"""

    REGISTER = "register"
    RESET_PASSWORD = "reset_password"


class NutritionParseSource(str, enum.Enum):
    """营养成分解析来源。"""

    TABLE_RECOGNITION = "table_recognition"
    OCR_TEXT = "ocr_text"
    LLM_FALLBACK = "llm_fallback"
    EMPTY = "empty"
    FAILED = "failed"


__all__ = ["NutritionParseSource", "TaskStatus", "VerificationType"]
