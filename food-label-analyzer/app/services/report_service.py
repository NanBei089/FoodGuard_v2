from __future__ import annotations

import math
import uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ReportNotFoundError
from app.models.analysis_task import AnalysisTask
from app.models.report import Report
from app.schemas.analysis_data import HealthAdviceItem, IngredientItem, NutritionData, RAGResults
from app.schemas.report import (
    AnalysisSchema,
    RagSummarySchema,
    ReportDetailResponseSchema,
    ReportListItemSchema,
    ReportListResponseSchema,
)
from app.services.storage_service import get_storage_service


def _safe_validate(model_cls, value: Any) -> Any:
    if value is None:
        return None
    try:
        return model_cls.model_validate(value)
    except ValidationError:
        return None


def _coerce_score(value: Any, fallback: int) -> int:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return fallback


def _coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _coerce_model_list(model_cls, value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    items: list[Any] = []
    for item in value:
        try:
            items.append(model_cls.model_validate(item))
        except ValidationError:
            continue
    return items


def _sanitize_artifact_urls(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    cleaned = {
        str(key): str(item)
        for key, item in value.items()
        if str(key).strip() and isinstance(item, str) and item.strip()
    }
    return cleaned or None


def _build_analysis(value: Any, score: int) -> AnalysisSchema:
    payload = value if isinstance(value, dict) else {}
    return AnalysisSchema(
        score=_coerce_score(payload.get("score"), score),
        summary=payload.get("summary") if isinstance(payload.get("summary"), str) else None,
        top_risks=_coerce_string_list(payload.get("top_risks")),
        ingredients=_coerce_model_list(IngredientItem, payload.get("ingredients")),
        health_advice=_coerce_model_list(HealthAdviceItem, payload.get("health_advice")),
    )


def _build_rag_summary(value: Any) -> RagSummarySchema:
    validated = _safe_validate(RAGResults, value)
    if validated is None:
        return RagSummarySchema(
            total_ingredients=0,
            retrieved_count=0,
            high_match_count=0,
            weak_match_count=0,
            empty_count=0,
        )

    results = list(validated.retrieval_results)
    total = validated.items_total or len(results)
    high = sum(1 for item in results if item.match_quality == "high")
    weak = sum(1 for item in results if item.match_quality == "weak")
    empty = sum(1 for item in results if item.match_quality == "empty")
    retrieved = sum(1 for item in results if item.retrieved)

    return RagSummarySchema(
        total_ingredients=max(total, 0),
        retrieved_count=retrieved,
        high_match_count=high,
        weak_match_count=weak,
        empty_count=empty,
    )


async def _build_image_url(image_key: str | None, image_url: str | None) -> str:
    if not image_key:
        return image_url or ""
    try:
        return await get_storage_service().get_presigned_url(image_key)
    except Exception:
        return image_url or ""


async def get_report_list(
    user_id: uuid.UUID,
    page: int,
    page_size: int,
    db: AsyncSession,
) -> ReportListResponseSchema:
    total_result = await db.execute(
        select(func.count()).select_from(Report).where(Report.user_id == user_id)
    )
    total = int(total_result.scalar_one())
    if total == 0:
        return ReportListResponseSchema(items=[], total=0, page=1, page_size=page_size)

    total_pages = math.ceil(total / page_size)
    safe_page = min(page, total_pages)

    result = await db.execute(
        select(
            Report.id.label("report_id"),
            Report.task_id,
            Report.score,
            Report.llm_output_json,
            Report.created_at,
            AnalysisTask.image_key,
            AnalysisTask.image_url,
        )
        .join(AnalysisTask, AnalysisTask.id == Report.task_id)
        .where(Report.user_id == user_id)
        .order_by(Report.created_at.desc())
        .offset((safe_page - 1) * page_size)
        .limit(page_size)
    )
    rows = result.all()

    items: list[ReportListItemSchema] = []
    for row in rows:
        llm_output = row.llm_output_json if isinstance(row.llm_output_json, dict) else {}
        items.append(
            ReportListItemSchema(
                report_id=row.report_id,
                task_id=row.task_id,
                score=row.score,
                summary=llm_output.get("summary") if isinstance(llm_output.get("summary"), str) else None,
                image_url=await _build_image_url(row.image_key, row.image_url),
                created_at=row.created_at,
            )
        )

    return ReportListResponseSchema(
        items=items,
        total=total,
        page=safe_page,
        page_size=page_size,
    )


async def get_report_detail(
    report_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> ReportDetailResponseSchema:
    result = await db.execute(
        select(Report, AnalysisTask.image_key, AnalysisTask.image_url)
        .join(AnalysisTask, AnalysisTask.id == Report.task_id)
        .where(Report.id == report_id, Report.user_id == user_id)
    )
    row = result.one_or_none()
    if row is None:
        raise ReportNotFoundError()

    report, image_key, image_url = row
    return ReportDetailResponseSchema(
        report_id=report.id,
        task_id=report.task_id,
        image_url=await _build_image_url(image_key, image_url),
        ingredients_text=report.ingredients_text,
        nutrition=_safe_validate(NutritionData, report.nutrition_json),
        nutrition_parse_source=report.nutrition_parse_source,
        analysis=_build_analysis(report.llm_output_json, report.score),
        rag_summary=_build_rag_summary(report.rag_results_json),
        artifact_urls=_sanitize_artifact_urls(report.artifact_urls),
        created_at=report.created_at,
    )


__all__ = ["get_report_detail", "get_report_list"]
