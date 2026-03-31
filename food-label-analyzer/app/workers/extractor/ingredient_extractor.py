from __future__ import annotations

import html
import json
import re
from typing import Iterable

import structlog
from openai import OpenAI

from app.core.config import get_settings
from app.workers.extractor.prompts.ingredient_extract import (
    build_ingredient_extract_prompt,
)

logger = structlog.get_logger(__name__)

TRIGGER_PATTERNS = [
    re.compile(pattern)
    for pattern in (
        r"\u914d\s*\u6599\s*\u8868\s*[\uff1a:]?\s*",
        r"\u914d\s*\u6599\s*(?:[\uff1a:]|\s{1,})+\s*",
        r"\u539f\s*\u8f85\s*\u6599\s*[\uff1a:]?\s*",
        r"\u4e3b\s*\u8981\s*\u539f\s*\u6599\s*[\uff1a:]?\s*",
        r"\u539f\s*\u6599\s*(?:[\uff1a:]|\s{1,})+\s*",
        r"(?<!\u8425\u517b)\u6210\s*\u5206\s*(?:[\uff1a:]|\s{1,})+\s*",
    )
]
STOP_PATTERNS = [
    re.compile(pattern)
    for pattern in (
        r"\u51c0\u542b\u91cf",
        r"\u751f\u4ea7\u65e5\u671f",
        r"\u4fdd\u8d28\u671f",
        r"\u50a8\u5b58\u65b9\u6cd5",
        r"\u50a8\u85cf\u65b9\u6cd5",
        r"\u4fdd\u5b58\u65b9\u6cd5",
        r"\u751f\u4ea7\u8bb8\u53ef",
        r"\u98df\u54c1\u751f\u4ea7\u8bb8\u53ef",
        r"\u6267\u884c\u6807\u51c6",
        r"\u4ea7\u54c1\u6807\u51c6",
        r"\u4ea7\u54c1\u540d\u79f0",
        r"\u4ea7\u54c1\u7c7b\u578b",
        r"\u5730\u5740",
        r"\u7535\u8bdd",
        r"\u5ba2\u670d",
        r"\u4ea7\u5730",
        r"\u8425\u517b\u6210\u5206",
        r"\u8425\u517b\u6210\u4efd",
        r"\n\s*\n",
    )
]
HTML_TABLE_PATTERN = re.compile(r"<table[\s\S]*?</table>", re.IGNORECASE)
HTML_LINEBREAK_TAG_PATTERN = re.compile(
    r"</?(?:div|p|br|li|section|article|ul|ol)[^>]*>",
    re.IGNORECASE,
)
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
INLINE_WHITESPACE_PATTERN = re.compile(r"[ \t\r\f\v]+")
MULTI_NEWLINE_PATTERN = re.compile(r"\n\s*\n+")
SEPARATORS = {"\u3001", "\uff0c", ","}
LEFT_BRACKETS = {"\uff08", "(", "\u3010"}
RIGHT_BRACKETS = {"\uff09", ")", "\u3011"}
COMPOUND_PATTERN = re.compile(
    r"^(.+?)[\uff08(\u3010](.+?)[\uff09)\u3011]$"
)
ADDITION_PATTERN = re.compile(
    r"[\uff08(]?\s*(?:\u6dfb\u52a0\u91cf|\u542b\u91cf)\s*[\u2265\u2267><]?\s*\d+\.?\d*\s*%?\s*[\uff09)]?"
)


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
    return cleaned.strip("\uff08\uff09\u3010\u3011\u3001\uff0c;\uff1b ")


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


def _sanitize_source_text(full_raw_text: str) -> str:
    normalized = html.unescape(full_raw_text or "")
    if not normalized.strip():
        return ""

    normalized = normalized.replace("\u3000", " ").replace("\xa0", " ")
    normalized = HTML_TABLE_PATTERN.sub("\n", normalized)
    normalized = HTML_LINEBREAK_TAG_PATTERN.sub("\n", normalized)
    normalized = HTML_TAG_PATTERN.sub("", normalized)
    normalized = INLINE_WHITESPACE_PATTERN.sub(" ", normalized)
    normalized = MULTI_NEWLINE_PATTERN.sub("\n", normalized)
    return normalized.strip()


def _locate_ingredients_text(full_raw_text: str) -> tuple[str, bool]:
    matches = [
        match
        for pattern in TRIGGER_PATTERNS
        for match in pattern.finditer(full_raw_text)
    ]
    if not matches:
        return "", False

    first_match = min(matches, key=lambda match: (match.start(), -len(match.group(0))))
    raw_ingredients = full_raw_text[first_match.end() :]
    raw_ingredients = raw_ingredients.lstrip("\uff1a: \t\r\n")
    end_positions = [
        match.start()
        for pattern in STOP_PATTERNS
        if (match := pattern.search(raw_ingredients))
    ]
    end_pos = min(end_positions) if end_positions else min(len(raw_ingredients), 2000)
    return raw_ingredients[:end_pos].strip(), True


def normalize_ingredients_text(full_raw_text: str) -> str:
    sanitized_text = _sanitize_source_text(full_raw_text)
    if not sanitized_text:
        return ""

    ingredients_text, found = _locate_ingredients_text(sanitized_text)
    if found and ingredients_text:
        return ingredients_text
    return sanitized_text


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
        candidate = item.strip()
        if not candidate:
            continue

        match = COMPOUND_PATTERN.match(candidate)
        if match:
            main_name = _clean_ingredient(match.group(1))
            sub_text = match.group(2)
            if main_name:
                expanded.append(main_name)
            for sub_item in re.split(r"[\u3001\uff0c,]", sub_text):
                cleaned_sub_item = _clean_ingredient(sub_item)
                if cleaned_sub_item:
                    expanded.append(cleaned_sub_item)
        else:
            cleaned_item = _clean_ingredient(candidate)
            if not cleaned_item:
                continue
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
    return _deduplicate_keep_order(
        [str(item).strip() for item in payload if str(item).strip()]
    )


def extract(full_raw_text: str) -> tuple[list[str], str]:
    normalized_text = _sanitize_source_text(full_raw_text)
    if not normalized_text:
        return [], ""

    ingredients_text, found = _locate_ingredients_text(normalized_text)
    if found and ingredients_text:
        ingredients_text = normalize_ingredients_text(ingredients_text)
        items = split_ingredients(ingredients_text)
        expanded = expand_compound_ingredients(items)
        if expanded:
            logger.info("ingredients_extracted_by_rule", count=len(expanded))
            return expanded, ingredients_text

    try:
        llm_result = _llm_extract(normalized_text)
        if llm_result:
            logger.info("ingredients_extracted_by_llm", count=len(llm_result))
            return llm_result, "(LLM\u63d0\u53d6)"
    except Exception as exc:
        logger.warning("ingredients_llm_failed", error=str(exc))

    logger.warning("ingredients_extraction_failed")
    return [], ""


__all__ = [
    "expand_compound_ingredients",
    "extract",
    "normalize_ingredients_text",
    "split_ingredients",
]
