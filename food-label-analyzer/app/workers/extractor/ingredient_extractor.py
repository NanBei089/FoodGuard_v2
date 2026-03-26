from __future__ import annotations

import json
import re
from typing import Iterable

import structlog
from openai import OpenAI

from app.core.config import get_settings
from app.workers.extractor.prompts.ingredient_extract import build_ingredient_extract_prompt


logger = structlog.get_logger(__name__)

TRIGGER_KEYWORDS = [
    "配料：",
    "配料:",
    "配料",
    "原料：",
    "原料:",
    "原料",
    "配料表：",
    "配料表:",
    "配料表",
    "原辅料：",
    "原辅料:",
    "原辅料",
    "成分：",
    "成分:",
    "成分",
    "主要原料：",
    "主要原料:",
    "主要原料",
    "配 料：",
    "配 料:",
    "配 料",
]
STOP_PATTERNS = [
    re.compile(pattern)
    for pattern in (
        r"净含量",
        r"生产日期",
        r"保质期",
        r"储存方法",
        r"储藏方法",
        r"保存方法",
        r"生产许可",
        r"食品生产许可",
        r"执行标准",
        r"产品标准",
        r"地址",
        r"电话",
        r"客服",
        r"产地",
        r"营养成分",
        r"营养成份",
        r"\n\s*\n",
    )
]
SEPARATORS = {"、", "，", ","}
LEFT_BRACKETS = {"（", "(", "【"}
RIGHT_BRACKETS = {"）", ")", "】"}
COMPOUND_PATTERN = re.compile(r"^(.+?)[（(【](.+?)[）)】]$")
ADDITION_PATTERN = re.compile(r"[（(]?\s*(?:添加量|含量)\s*[≥≤><]?\s*\d+\.?\d*\s*%?\s*[）)]?")


def _get_llm_client() -> OpenAI:
    settings = get_settings()
    return OpenAI(
        base_url=settings.DEEPSEEK_BASE_URL,
        api_key=settings.DEEPSEEK_API_KEY.get_secret_value(),
        timeout=settings.DEEPSEEK_TIMEOUT,
        max_retries=settings.DEEPSEEK_MAX_RETRIES,
    )


def _clean_ingredient(text: str) -> str:
    cleaned = ADDITION_PATTERN.sub("", text).strip()
    return cleaned.strip("，,、；; ")


def _deduplicate_keep_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _locate_ingredients_text(full_raw_text: str) -> tuple[str, bool]:
    first_match: tuple[int, str] | None = None
    for keyword in TRIGGER_KEYWORDS:
        index = full_raw_text.find(keyword)
        if index != -1 and (first_match is None or index < first_match[0]):
            first_match = (index, keyword)

    if first_match is None:
        return "", False

    start_index = first_match[0] + len(first_match[1])
    raw_ingredients = full_raw_text[start_index:]
    raw_ingredients = raw_ingredients.lstrip("：: \t\r\n")
    end_positions = [match.start() for pattern in STOP_PATTERNS if (match := pattern.search(raw_ingredients))]
    end_pos = min(end_positions) if end_positions else min(len(raw_ingredients), 2000)
    return raw_ingredients[:end_pos].strip(), True


def split_ingredients(text: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    depth = 0

    for char in text:
        if char in LEFT_BRACKETS:
            depth += 1
            current.append(char)
        elif char in RIGHT_BRACKETS:
            depth = max(0, depth - 1)
            current.append(char)
        elif char in SEPARATORS and depth == 0:
            item = "".join(current).strip()
            if item:
                items.append(item)
            current = []
        else:
            current.append(char)

    tail = "".join(current).strip()
    if tail:
        items.append(tail)
    return items


def expand_compound_ingredients(items: list[str]) -> list[str]:
    expanded: list[str] = []
    for item in items:
        cleaned_item = _clean_ingredient(item)
        if not cleaned_item:
            continue

        match = COMPOUND_PATTERN.match(cleaned_item)
        if match:
            main_name = _clean_ingredient(match.group(1))
            sub_text = match.group(2)
            if main_name:
                expanded.append(main_name)
            for sub_item in re.split(r"[、，,]", sub_text):
                cleaned_sub_item = _clean_ingredient(sub_item)
                if cleaned_sub_item:
                    expanded.append(cleaned_sub_item)
        else:
            expanded.append(cleaned_item)
    return _deduplicate_keep_order(expanded)


def _llm_extract(full_raw_text: str) -> list[str]:
    settings = get_settings()
    prompt = build_ingredient_extract_prompt()
    response = _get_llm_client().chat.completions.create(
        model=settings.DEEPSEEK_MODEL,
        temperature=0,
        max_tokens=500,
        messages=[
            {"role": "system", "content": "Return a JSON array only."},
            {"role": "user", "content": prompt.format(full_raw_text=full_raw_text)},
        ],
    )
    content = response.choices[0].message.content or "[]"
    payload = json.loads(content)
    if not isinstance(payload, list):
        return []
    return _deduplicate_keep_order([str(item).strip() for item in payload if str(item).strip()])


def extract(full_raw_text: str) -> tuple[list[str], str]:
    if not full_raw_text or not full_raw_text.strip():
        return [], ""

    ingredients_text, found = _locate_ingredients_text(full_raw_text)
    if found and ingredients_text:
        items = split_ingredients(ingredients_text)
        expanded = expand_compound_ingredients(items)
        if expanded:
            logger.info("ingredients_extracted_by_rule", count=len(expanded))
            return expanded, ingredients_text

    try:
        llm_result = _llm_extract(full_raw_text)
        if llm_result:
            logger.info("ingredients_extracted_by_llm", count=len(llm_result))
            return llm_result, "(LLM提取)"
    except Exception as exc:
        logger.warning("ingredients_llm_failed", error=str(exc))

    logger.warning("ingredients_extraction_failed")
    return [], ""


__all__ = ["expand_compound_ingredients", "extract", "split_ingredients"]
