"""Aggregate model imports for Alembic metadata registration."""

from app.models.analysis_task import AnalysisTask
from app.models.email_verification import EmailVerification
from app.models.enums import NutritionParseSource, TaskStatus, VerificationType
from app.models.password_reset import PasswordResetToken
from app.models.report import Report
from app.models.user import User


__all__ = [
    "AnalysisTask",
    "EmailVerification",
    "NutritionParseSource",
    "PasswordResetToken",
    "Report",
    "TaskStatus",
    "User",
    "VerificationType",
]
