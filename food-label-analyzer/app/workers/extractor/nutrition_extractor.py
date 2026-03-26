from __future__ import annotations

import json
import re
from typing import Any

import structlog
from openai import OpenAI

from app.core.config import get_settings
from app.schemas.analysis_data import NutritionData
from app.workers.extractor.prompts.nutrition_parse import build_nutrition_parse_prompt


logger = structlog.get_logger(__name__)

NUTRIENT_ALIASES: dict[str, tuple[str, ...]] = {
    "能量": ("能量", "热量", "energy"),
    "蛋白质": ("蛋白质", "protein"),
    "脂肪": ("脂肪", "总脂肪", "fat"),
    "碳水化合物": ("碳水化合物", "碳水", "carbohydrate"),
    "钠": ("钠", "sodium"),
    "糖": ("糖", "总糖"),
    "膳食纤维": ("膳食纤维", "纤维"),
    "反式脂肪酸": ("反式脂肪酸",),
    "饱和脂肪": ("饱和脂肪", "饱和脂肪酸"),
    "胆固醇": ("胆固醇",),
    "钙": ("钙",),
    "铁": ("铁",),
    "维生素C": ("维生素C", "维C", "vc"),
}
SUPPORTED_UNITS = ("kJ", "kcal", "g", "mg", "μg", "ug")
VALUE_UNIT_PATTERN = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>kJ|kcal|g|mg|μg|ug)",
    re.IGNORECASE,
)
NRV_PATTERN = re.compile(r"(?P<nrv>\d+(?:\.\d+)?)\s*%")
SERVING_SIZE_PATTERNS = (
    re.compile(r"(每\s*\d+(?:\.\d+)?\s*(?:g|克|kg|ml|mL|毫升))", re.IGNORECASE),
    re.compile(r"(每份\s*\d+(?:\.\d+)?\s*(?:g|克|kg|ml|mL|毫升))", re.IGNORECASE),
)


def _get_llm_client() -> OpenAI:
    settings = get_settings()
    return OpenAI(
        base_url=settings.DEEPSEEK_BASE_URL,
        api_key=settings.DEEPSEEK_API_KEY.get_secret_value(),
        timeout=settings.DEEPSEEK_TIMEOUT,
        max_retries=settings.DEEPSEEK_MAX_RETRIES,
    )


def _build_result(items: list[dict[str, Any]], serving_size: str | None, parse_method: str) -> dict[str, Any]:
    return NutritionData(
        items=items,
        serving_size=serving_size,
        parse_method=parse_method,
    ).model_dump()


def _normalize_nutrient_name(raw_name: str) -> str | None:
    normalized = raw_name.strip().lower().replace(" ", "")
    for canonical, aliases in NUTRIENT_ALIASES.items():
        alias_set = {alias.lower().replace(" ", "") for alias in aliases}
        if normalized in alias_set:
            return canonical
    return None


def _collect_text_nodes(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            parts.extend(_collect_text_nodes(item))
        return parts
    if isinstance(value, dict):
        if "rows" in value and isinstance(value["rows"], list):
            rows: list[str] = []
            for row in value["rows"]:
                row_parts = _collect_text_nodes(row)
                if row_parts:
                    rows.append(" ".join(row_parts))
            return rows

        if "table" in value and isinstance(value["table"], list):
            table_rows: list[str] = []
            for item in value["table"]:
                row_parts = _collect_text_nodes(item)
                if row_parts:
                    table_rows.append(" ".join(row_parts))
            return table_rows

        parts: list[str] = []
        for key, item in value.items():
            parts.extend(_collect_text_nodes(item))
        return parts
    return []


def _find_serving_size(text: str) -> str | None:
    for pattern in SERVING_SIZE_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def _parse_text_content(text: str, method: str) -> dict[str, Any] | None:
    if not text or not text.strip():
        return None

    serving_size = _find_serving_size(text)
    seen_names: set[str] = set()
    items: list[dict[str, Any]] = []

    candidate_lines = [line.strip() for line in re.split(r"[\r\n]+", text) if line.strip()]
    if len(candidate_lines) == 1:
        candidate_lines = [segment.strip() for segment in re.split(r"[；;]", text) if segment.strip()]

    for line in candidate_lines:
        compact_line = re.sub(r"\s+", "", line)
        for canonical, aliases in NUTRIENT_ALIASES.items():
            alias_match = next(
                (alias for alias in aliases if alias.lower().replace(" ", "") in compact_line.lower()),
                None,
            )
            if not alias_match or canonical in seen_names:
                continue

            value_match = VALUE_UNIT_PATTERN.search(line)
            if not value_match:
                continue

            unit = value_match.group("unit")
            if unit.lower() == "ug":
                unit = "μg"
            if unit not in SUPPORTED_UNITS and unit != "μg":
                continue

            nrv_match = NRV_PATTERN.search(line[value_match.end() :]) or NRV_PATTERN.search(line)
            items.append(
                {
                    "name": canonical,
                    "value": value_match.group("value"),
                    "unit": unit,
                    "daily_reference_percent": f"{nrv_match.group('nrv')}%" if nrv_match else None,
                },
            )
            seen_names.add(canonical)
            break

    if not items:
        return None
    return _build_result(items, serving_size, method)


def _parse_from_table_result(table_result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not table_result:
        return None
    table_json = table_result.get("table_json")

    if isinstance(table_json, dict):
        text_chunks = _collect_text_nodes(table_json)
        if text_chunks:
            text = "\n".join(str(chunk) for chunk in text_chunks if chunk)
            result = _parse_text_content(text, "table_recognition")
            if result:
                return result

    if isinstance(table_json, dict) and "table" in table_json:
        items = []
        for item in table_json.get("table", []):
            if isinstance(item, dict):
                items.append({
                    "name": item.get("name", ""),
                    "value": str(item.get("value", "")),
                    "unit": item.get("unit", "g"),
                    "daily_reference_percent": item.get("nrv"),
                })
        if items:
            return _build_result(items, table_json.get("serving_size"), "table_recognition")

    return None


def _parse_from_ocr_text(nutrition_raw_text: str | None) -> dict[str, Any] | None:
    if not nutrition_raw_text:
        return None
    return _parse_text_content(nutrition_raw_text, "ocr_text")


def _llm_fallback(nutrition_raw_text: str | None) -> dict[str, Any] | None:
    if not nutrition_raw_text or not nutrition_raw_text.strip():
        return None

    prompt = build_nutrition_parse_prompt()
    settings = get_settings()
    try:
        response = _get_llm_client().chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            temperature=0,
            max_tokens=600,
            messages=[
                {"role": "system", "content": "Return valid JSON only."},
                {"role": "user", "content": prompt.format(nutrition_raw_text=nutrition_raw_text)},
            ],
        )
        content = response.choices[0].message.content or "{}"
        payload = json.loads(content)
        if not isinstance(payload, dict):
            return None
        payload["parse_method"] = "llm_fallback"
        result = NutritionData.model_validate(payload)
        return result.model_dump()
    except Exception as exc:
        logger.warning("nutrition_llm_fallback_failed", error=str(exc))
        return None


def parse(table_result, ocr_fallback_text: str | None = None) -> dict[str, Any]:
    table_data = table_result.model_dump() if hasattr(table_result, "model_dump") else table_result
    if isinstance(table_data, dict):
        result = _parse_from_table_result(table_data)
        if result:
            logger.info("table_recognition_parsed", items=len(result["items"]))
            return result

    result = _parse_from_ocr_text(ocr_fallback_text)
    if result:
        logger.info("nutrition_rule_parsed", items=len(result["items"]))
        return result

    result = _llm_fallback(ocr_fallback_text)
    if result:
        logger.info("nutrition_llm_fallback", items=len(result["items"]))
        return result

    if not table_data and not ocr_fallback_text:
        logger.info("nutrition_parse_empty")
        return _build_result([], None, "empty")

    logger.warning("nutrition_parse_failed")
    return _build_result([], None, "failed")


__all__ = ["parse"]
