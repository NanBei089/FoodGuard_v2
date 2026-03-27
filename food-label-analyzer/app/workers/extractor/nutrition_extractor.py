from __future__ import annotations

import json
import re
from typing import Any

import structlog
from openai import OpenAI

from app.core.config import get_settings
from app.schemas.analysis_data import NutritionData
from app.workers.extractor.prompts.nutrition_table_llm_parse import (
    build_nutrition_table_llm_parse_prompt,
)

logger = structlog.get_logger(__name__)


def _get_llm_client() -> OpenAI:
    settings = get_settings()
    return OpenAI(
        base_url=settings.DEEPSEEK_BASE_URL,
        api_key=settings.DEEPSEEK_API_KEY.get_secret_value(),
        timeout=settings.DEEPSEEK_TIMEOUT,
        max_retries=settings.DEEPSEEK_MAX_RETRIES,
    )


def _build_result(
    items: list[dict[str, Any]],
    serving_size: str | None,
    parse_method: str,
    advice_summary: str | None = None,
) -> dict[str, Any]:
    return NutritionData(
        items=items,
        serving_size=serving_size,
        advice_summary=advice_summary,
        parse_method=parse_method,
    ).model_dump()


def _extract_json_payload(content: str) -> dict[str, Any] | None:
    if not content:
        return None

    normalized = content.strip()
    if normalized.startswith("```"):
        fenced_match = re.search(
            r"```(?:json)?\s*(\{[\s\S]*\})\s*```",
            normalized,
            re.IGNORECASE,
        )
        if fenced_match:
            normalized = fenced_match.group(1).strip()

    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError:
        object_match = re.search(r"\{[\s\S]*\}", normalized)
        if not object_match:
            return None
        try:
            payload = json.loads(object_match.group(0))
        except json.JSONDecodeError:
            return None

    if not isinstance(payload, dict):
        return None
    return payload


def _sanitize_table_result(table_result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(table_result, dict):
        return None

    table_json = table_result.get("table_json")
    if isinstance(table_json, dict):
        return table_json
    return table_result


def _serialize_inputs(
    table_result: dict[str, Any] | None,
    nutrition_raw_text: str | None,
) -> dict[str, str]:
    sanitized_table_result = _sanitize_table_result(table_result)
    return {
        "table_result_json": json.dumps(
            sanitized_table_result or {}, ensure_ascii=False, indent=2
        ),
        "nutrition_raw_text": (
            nutrition_raw_text.strip()
            if nutrition_raw_text and nutrition_raw_text.strip()
            else "(无补充 OCR 文本)"
        ),
    }


def _resolve_parse_method(
    table_result: dict[str, Any] | None,
    nutrition_raw_text: str | None,
) -> str:
    if _sanitize_table_result(table_result):
        return "table_recognition"
    if nutrition_raw_text and nutrition_raw_text.strip():
        return "ocr_text"
    return "empty"


def _render_prompt(template: str, inputs: dict[str, str]) -> str:
    rendered = template
    for key, value in inputs.items():
        rendered = rendered.replace(f"{{{key}}}", value)
    return rendered


def _llm_parse(
    table_result: dict[str, Any] | None,
    nutrition_raw_text: str | None,
) -> dict[str, Any] | None:
    parse_method = _resolve_parse_method(table_result, nutrition_raw_text)
    if parse_method == "empty":
        return _build_result([], None, "empty")

    settings = get_settings()
    prompt = build_nutrition_table_llm_parse_prompt()
    inputs = _serialize_inputs(table_result, nutrition_raw_text)
    rendered_prompt = _render_prompt(prompt, inputs)

    try:
        response = _get_llm_client().chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            temperature=0,
            max_tokens=1200,
            messages=[
                {"role": "system", "content": "Return valid JSON only."},
                {"role": "user", "content": rendered_prompt},
            ],
        )
        content = response.choices[0].message.content or "{}"
        payload = _extract_json_payload(content)
        if payload is None:
            return None
        payload["parse_method"] = parse_method
        result = NutritionData.model_validate(payload)
        return result.model_dump()
    except Exception as exc:
        logger.warning("nutrition_llm_parse_failed", error=str(exc))
        return None


def parse(table_result, ocr_fallback_text: str | None = None) -> dict[str, Any]:
    table_data = (
        table_result.model_dump()
        if hasattr(table_result, "model_dump")
        else table_result
    )
    if not isinstance(table_data, dict):
        table_data = None

    result = _llm_parse(table_data, ocr_fallback_text)
    if result:
        logger.info(
            "nutrition_llm_parsed",
            parse_method=result["parse_method"],
            items=len(result["items"]),
        )
        return result

    if table_data and ocr_fallback_text:
        result = _llm_parse(None, ocr_fallback_text)
        if result:
            logger.info(
                "nutrition_llm_parsed_from_text",
                parse_method=result["parse_method"],
                items=len(result["items"]),
            )
            return result

    if not table_data and not ocr_fallback_text:
        logger.info("nutrition_parse_empty")
        return _build_result([], None, "empty")

    logger.warning("nutrition_parse_failed")
    return _build_result([], None, "failed")


__all__ = ["parse", "_llm_parse"]
