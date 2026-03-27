from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ReportNotFoundError
from app.models.analysis_task import AnalysisTask
from app.models.report import Report
from app.schemas.analysis_data import (
    HazardItem,
    HealthAdviceItem,
    IngredientItem,
    NutritionData,
    NutritionItem,
    RAGResults,
)
from app.schemas.report import (
    AnalysisSchema,
    NutritionTableRowSchema,
    NutritionTableSchema,
    RagSummarySchema,
    ReportDetailResponseSchema,
    ReportListItemSchema,
    ReportListResponseSchema,
)
from app.services.storage_service import get_storage_service

NUTRIENT_DEFINITIONS: dict[str, dict[str, Any]] = {
    "energy": {
        "cn": "能量",
        "en": "Energy",
        "aliases": ["能量", "energy", "热量", "千焦", "kj", "kcal"],
        "order": 10,
        "kind": "neutral",
    },
    "protein": {
        "cn": "蛋白质",
        "en": "Protein",
        "aliases": ["蛋白质", "protein"],
        "order": 20,
        "kind": "positive",
    },
    "fat": {
        "cn": "脂肪",
        "en": "Total Fat",
        "aliases": ["总脂肪", "脂肪", "totalfat", "fat"],
        "order": 30,
        "kind": "negative",
    },
    "saturated_fat": {
        "cn": "饱和脂肪",
        "en": "Saturated Fat",
        "aliases": ["饱和脂肪酸", "饱和脂肪", "saturatedfat"],
        "order": 31,
        "kind": "strict_negative",
        "parent": "fat",
    },
    "trans_fat": {
        "cn": "反式脂肪",
        "en": "Trans Fat",
        "aliases": ["反式脂肪酸", "反式脂肪", "transfat", "transfattyacid"],
        "order": 32,
        "kind": "strict_negative",
        "parent": "fat",
    },
    "cholesterol": {
        "cn": "胆固醇",
        "en": "Cholesterol",
        "aliases": ["胆固醇", "cholesterol"],
        "order": 33,
        "kind": "strict_negative",
    },
    "carb": {
        "cn": "碳水化合物",
        "en": "Carbohydrates",
        "aliases": ["碳水化合物", "carbohydrates", "carbohydrate"],
        "order": 40,
        "kind": "neutral",
    },
    "sugar": {
        "cn": "糖",
        "en": "Sugars",
        "aliases": ["添加糖", "总糖", "糖", "sugars", "sugar"],
        "order": 41,
        "kind": "negative",
        "parent": "carb",
    },
    "fiber": {
        "cn": "膳食纤维",
        "en": "Dietary Fiber",
        "aliases": ["膳食纤维", "纤维", "dietaryfiber", "fiber"],
        "order": 42,
        "kind": "positive",
        "parent": "carb",
    },
    "sodium": {
        "cn": "钠",
        "en": "Sodium",
        "aliases": ["钠", "sodium"],
        "order": 50,
        "kind": "strict_negative",
    },
    "calcium": {
        "cn": "钙",
        "en": "Calcium",
        "aliases": ["钙", "calcium"],
        "order": 60,
        "kind": "positive",
    },
    "iron": {
        "cn": "铁",
        "en": "Iron",
        "aliases": ["铁", "iron"],
        "order": 61,
        "kind": "positive",
    },
    "vitamin_c": {
        "cn": "维生素C",
        "en": "Vitamin C",
        "aliases": ["维生素c", "vitaminc"],
        "order": 62,
        "kind": "positive",
    },
}

POSITIVE_NUTRIENTS = {"protein", "fiber", "calcium", "iron", "vitamin_c"}
NEGATIVE_NUTRIENTS = {
    "fat",
    "saturated_fat",
    "trans_fat",
    "sodium",
    "sugar",
    "cholesterol",
}
_NUTRIENT_ALIAS_MATCHERS = sorted(
    (
        (_alias, key)
        for key, definition in NUTRIENT_DEFINITIONS.items()
        for _alias in [
            re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", alias.lower())
            for alias in definition["aliases"]
        ]
        if _alias
    ),
    key=lambda item: len(item[0]),
    reverse=True,
)


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


def _normalize_nutrient_name(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", (value or "").lower())


def _resolve_nutrient_key(name: str) -> str:
    normalized = _normalize_nutrient_name(name)
    for alias, key in _NUTRIENT_ALIAS_MATCHERS:
        if alias and alias in normalized:
            return key
    return normalized or "unknown"


def _parse_percentage(value: str | None) -> float | None:
    if not value:
        return None
    cleaned = value.strip().replace("％", "%").replace("%", "")
    try:
        return float(cleaned)
    except (TypeError, ValueError):
        return None


def _format_percentage(value: float | None) -> str | None:
    if value is None:
        return None
    rounded = round(value, 1)
    if rounded.is_integer():
        return f"{int(rounded)}%"
    return f"{rounded}%"


def _parse_float(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _format_amount(value: str, unit: str) -> str:
    amount = str(value).strip()
    normalized_unit = str(unit or "").strip()
    return f"{amount} {normalized_unit}".strip()


def _format_serving_basis(serving_size: str | None) -> str:
    if not serving_size:
        return "每100克 (Per 100g)"

    raw = serving_size.strip()
    normalized = _normalize_nutrient_name(raw)
    if "100克" in raw or "100g" in normalized:
        return "每100克 (Per 100g)"
    if "100毫升" in raw or "100ml" in normalized:
        return "每100毫升 (Per 100ml)"
    if raw.startswith("每份") or "perserving" in normalized or "份" in raw:
        return f"{raw} (Per serving)"
    return raw


def _classify_positive_nutrient(nrv: float | None) -> tuple[str, str]:
    if nrv is None:
        return "neutral", "可作为日常补充来源"
    if nrv >= 20:
        return "good", "优质营养，含量较高"
    if nrv >= 10:
        return "good", "含量适中，可作为补充来源"
    return "neutral", "含量一般，可搭配其他食物补充"


def _classify_strict_negative_nutrient(
    key: str,
    nrv: float | None,
    amount_value: float | None,
) -> tuple[str, str]:
    if key == "trans_fat":
        if amount_value is not None and amount_value <= 0:
            return "good", "未检出或极低，相对友好"
        return "warning", "存在反式脂肪，建议减少摄入"

    if nrv is None:
        if key == "sodium":
            return "attention", "缺少 NRV，仍需注意总摄入量"
        return "neutral", "建议结合整体饮食控制摄入"

    if key == "sodium":
        if nrv >= 30:
            return "warning", "含量较高，需控制"
        if nrv >= 15:
            return "attention", "含量不低，注意控制"
        return "neutral", f"日常量的{_format_percentage(nrv)}，适量"

    if key in {"saturated_fat", "cholesterol"}:
        if nrv >= 25:
            return "warning", "含量较高，建议减少摄入"
        if nrv >= 10:
            return "attention", "含量不低，注意控制"
        return "neutral", "含量可控，注意整体搭配"

    return "neutral", "建议适量摄入"


def _classify_negative_nutrient(key: str, nrv: float | None) -> tuple[str, str]:
    if nrv is None:
        return "neutral", "建议结合总摄入量综合判断"

    if key == "fat":
        if nrv >= 40:
            return "warning", "脂肪较高，需控制"
        if nrv >= 20:
            return "attention", "中等含量，注意控制"
        return "neutral", "含量适中"

    if key == "sugar":
        if nrv >= 25:
            return "warning", "糖含量偏高，建议减少摄入"
        if nrv >= 10:
            return "attention", "适量摄入，注意频率"
        return "good", "适量摄入"

    return "neutral", "建议适量摄入"


def _classify_neutral_nutrient(key: str, nrv: float | None) -> tuple[str, str]:
    if nrv is None:
        return "neutral", "建议结合配料与总能量综合判断"

    if key == "energy":
        if nrv >= 30:
            return "warning", "能量较高，注意食用量"
        if nrv >= 15:
            return "neutral", f"日常量的{_format_percentage(nrv)}，适量"
        return "good", "能量负担较轻"

    if key == "carb":
        if nrv >= 25:
            return "attention", "含量不低，注意搭配"
        return "neutral", "含量适中"

    return "neutral", "含量适中"


def _build_nutrition_recommendation(
    nutrient_key: str,
    nrv: float | None,
    amount_value: float | None,
) -> tuple[str, str]:
    if nutrient_key in POSITIVE_NUTRIENTS:
        return _classify_positive_nutrient(nrv)
    if nutrient_key in {"sodium", "saturated_fat", "trans_fat", "cholesterol"}:
        return _classify_strict_negative_nutrient(nutrient_key, nrv, amount_value)
    if nutrient_key in {"fat", "sugar"}:
        return _classify_negative_nutrient(nutrient_key, nrv)
    return _classify_neutral_nutrient(nutrient_key, nrv)


def _build_nutrition_advice_summary(rows: list[NutritionTableRowSchema]) -> str | None:
    top_rows = [row for row in rows if not row.is_child]
    warnings = [row for row in top_rows if row.level == "warning"]
    attentions = [row for row in top_rows if row.level == "attention"]
    positives = [row for row in top_rows if row.level == "good"]

    if warnings or attentions:
        concern_rows = (warnings + attentions)[:2]
        concern_text = "、".join(
            f"{row.name_cn}{f'（占NRV的{row.nrv_label}）' if row.nrv_label else ''}"
            for row in concern_rows
        )
        positive_row = next((row for row in positives if row.nutrient_key == "protein"), None)
        positive_text = (
            f" 同时，{positive_row.name_cn}表现较好，可作为补充来源。"
            if positive_row is not None
            else ""
        )
        return (
            f"该食品{concern_text}需要重点关注。建议控制单次食用量，避免与其他高负担食品叠加摄入，"
            f"并搭配蔬菜、水果或低盐食物一起食用。{positive_text}".strip()
        )

    if positives:
        positive_rows = positives[:2]
        positive_text = "、".join(row.name_cn for row in positive_rows)
        return (
            f"该食品{positive_text}表现相对较好，可作为日常饮食中的补充来源。"
            "仍建议结合整体配料和总能量控制食用频率。"
        )

    return "当前营养结构整体中性，建议结合配料风险和人群建议综合判断是否适合长期购买。"


def _build_nutrition_table(nutrition_data: NutritionData | None) -> NutritionTableSchema | None:
    if not nutrition_data or not nutrition_data.items:
        return None

    rows_with_order: list[tuple[int, NutritionTableRowSchema]] = []
    for index, item in enumerate(nutrition_data.items):
        nutrient_key = _resolve_nutrient_key(item.name)
        definition = NUTRIENT_DEFINITIONS.get(nutrient_key, {})
        nrv = _parse_percentage(item.daily_reference_percent)
        amount_value = _parse_float(item.value)
        fallback_level, fallback_recommendation = _build_nutrition_recommendation(
            nutrient_key,
            nrv,
            amount_value,
        )
        level = item.level or fallback_level
        recommendation = item.recommendation or fallback_recommendation
        name_cn = str(definition.get("cn") or item.name)
        name_en = definition.get("en")
        rows_with_order.append(
            (
                int(definition.get("order", 900 + index)),
                NutritionTableRowSchema(
                    nutrient_key=nutrient_key,
                    name_cn=name_cn,
                    name_en=name_en,
                    display_name=f"{name_cn} / {name_en}" if name_en else name_cn,
                    amount=_format_amount(item.value, item.unit),
                    nrv_percent=nrv,
                    nrv_label=_format_percentage(nrv),
                    recommendation=recommendation,
                    level=level,
                    is_child=bool(definition.get("parent")),
                    parent_key=definition.get("parent"),
                ),
            )
        )

    rows = [row for _, row in sorted(rows_with_order, key=lambda item: item[0])]
    serving_basis = _format_serving_basis(nutrition_data.serving_size)
    return NutritionTableSchema(
        subtitle=serving_basis,
        serving_basis=serving_basis,
        parse_source=nutrition_data.parse_method,
        rows=rows,
        advice_summary=nutrition_data.advice_summary or _build_nutrition_advice_summary(rows),
    )


def _build_analysis(value: Any, score: int) -> AnalysisSchema:
    payload = value if isinstance(value, dict) else {}
    return AnalysisSchema(
        score=_coerce_score(payload.get("score"), score),
        summary=(
            payload.get("summary") if isinstance(payload.get("summary"), str) else None
        ),
        hazards=_coerce_model_list(HazardItem, payload.get("hazards")),
        benefits=_coerce_string_list(payload.get("benefits")),
        ingredients=_coerce_model_list(IngredientItem, payload.get("ingredients")),
        health_advice=_coerce_model_list(
            HealthAdviceItem, payload.get("health_advice")
        ),
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
        select(func.count())
        .select_from(Report)
        .where(
            Report.user_id == user_id,
            Report.deleted_at.is_(None),
        )
    )
    total = int(total_result.scalar_one())
    if total == 0:
        return ReportListResponseSchema(items=[], total=0, page=1, page_size=page_size)

    total_pages = (total + page_size - 1) // page_size
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
        .where(Report.user_id == user_id, Report.deleted_at.is_(None))
        .order_by(Report.created_at.desc())
        .offset((safe_page - 1) * page_size)
        .limit(page_size)
    )
    rows = result.all()

    items: list[ReportListItemSchema] = []
    for row in rows:
        llm_output = (
            row.llm_output_json if isinstance(row.llm_output_json, dict) else {}
        )
        items.append(
            ReportListItemSchema(
                report_id=row.report_id,
                task_id=row.task_id,
                score=row.score,
                summary=(
                    llm_output.get("summary")
                    if isinstance(llm_output.get("summary"), str)
                    else None
                ),
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


def _format_nutrition(nutrition_data: NutritionData | None) -> dict[str, str]:
    if not nutrition_data or not nutrition_data.items:
        return {}
    
    formatted = {}
    for item in nutrition_data.items:
        formatted[item.name] = f"{item.value}{item.unit}"
    
    if nutrition_data.serving_size:
        formatted["份量"] = nutrition_data.serving_size
        
    return formatted


async def get_report_detail(
    report_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> ReportDetailResponseSchema:
    result = await db.execute(
        select(Report, AnalysisTask.image_key, AnalysisTask.image_url)
        .join(AnalysisTask, AnalysisTask.id == Report.task_id)
        .where(
            Report.id == report_id,
            Report.user_id == user_id,
            Report.deleted_at.is_(None),
        )
    )
    row = result.one_or_none()
    if row is None:
        raise ReportNotFoundError()

    report, image_key, image_url = row
    validated_nutrition = _safe_validate(NutritionData, report.nutrition_json)
    return ReportDetailResponseSchema(
        report_id=report.id,
        task_id=report.task_id,
        image_url=await _build_image_url(image_key, image_url),
        ingredients_text=report.ingredients_text,
        nutrition=_format_nutrition(validated_nutrition),
        nutrition_table=_build_nutrition_table(validated_nutrition),
        nutrition_parse_source=report.nutrition_parse_source,
        analysis=_build_analysis(report.llm_output_json, report.score),
        rag_summary=_build_rag_summary(report.rag_results_json),
        artifact_urls=_sanitize_artifact_urls(report.artifact_urls),
        created_at=report.created_at,
    )


async def delete_report(
    report_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession
) -> None:
    result = await db.execute(
        select(Report).where(
            Report.id == report_id,
            Report.user_id == user_id,
            Report.deleted_at.is_(None),
        )
    )
    report = result.scalar_one_or_none()
    if report is None:
        raise ReportNotFoundError()

    report.deleted_at = datetime.now(timezone.utc)
    await db.flush()


__all__ = ["delete_report", "get_report_detail", "get_report_list"]
