from __future__ import annotations

import enum


class TaskStatus(str, enum.Enum):
    """Forward-looking task status enum reserved for DOC-02 and DOC-04."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class VerificationType(str, enum.Enum):
    """Forward-looking email verification type enum reserved for DOC-02 and DOC-03."""

    REGISTER = "register"
    RESET_PASSWORD = "reset_password"


class NutritionParseSource(str, enum.Enum):
    """Forward-looking nutrition parse source enum reserved for DOC-05 and DOC-06."""

    TABLE_RECOGNITION = "table_recognition"
    OCR_TEXT = "ocr_text"
    LLM_FALLBACK = "llm_fallback"
    EMPTY = "empty"
    FAILED = "failed"


__all__ = ["NutritionParseSource", "TaskStatus", "VerificationType"]
