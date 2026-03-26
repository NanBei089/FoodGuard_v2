from __future__ import annotations

import re
from typing import Any

from app.workers.extractor.rule_config import (
    INGREDIENT_BOUNDARY_RE,
    INGREDIENT_END_RE,
    INGREDIENT_LABEL_RE,
    INGREDIENT_TEXT_LIMIT,
    MANUFACTURER_GROUP_TOPICS,
    MANUFACTURER_LINE_RE,
    NOISE_LINE_RE,
    NUTRITION_HEADER_RE,
    OTHER_TOPIC_ORDER,
    OTHER_TOPIC_PATTERNS,
    SPACE_RE,
    TOPIC_TRIM_EDGE_RE,
)


def extract_ingredient_topic(
    clean_text: str,
    flat_text: str,
    clean_lines: list[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(clean_text, str) or not isinstance(flat_text, str):
        raise ValueError("extract_ingredient_topic 需要 clean_text 与 flat_text 字符串输入。")

    lines = _prepare_lines(clean_text=clean_text, clean_lines=clean_lines)
    if not lines:
        raise ValueError("clean_text 清洗结果为空，无法执行配料提取。")

    for index, line in enumerate(lines):
        match = INGREDIENT_LABEL_RE.search(line)
        if not match:
            continue
        if "营养" in line and NUTRITION_HEADER_RE.search(line[: match.end() + 4]):
            continue

        start_anchor = _normalize_anchor(match.group("anchor"))
        fragments: list[str] = []
        end_anchor = ""

        first_fragment, inline_anchor = _trim_ingredient_fragment(line[match.end() :])
        if first_fragment:
            fragments.append(first_fragment)
        if inline_anchor:
            end_anchor = inline_anchor
        else:
            for next_line in lines[index + 1 :]:
                if _is_noise_line(next_line):
                    break
                boundary_anchor = _ingredient_boundary_anchor(next_line)
                if boundary_anchor:
                    end_anchor = boundary_anchor
                    break
                fragment, inline_anchor = _trim_ingredient_fragment(next_line)
                if fragment:
                    fragments.append(fragment)
                if inline_anchor:
                    end_anchor = inline_anchor
                    break
                if len("".join(fragments)) >= INGREDIENT_TEXT_LIMIT:
                    break

        text = _join_fragments(fragments, separator="")[:INGREDIENT_TEXT_LIMIT]
        return {
            "found": bool(text),
            "text": text,
            "trace": {
                "start_anchor": start_anchor,
                "end_anchor": end_anchor,
            },
        }

    return {
        "found": False,
        "text": "",
        "trace": {
            "start_anchor": "",
            "end_anchor": "",
        },
    }


def extract_other_topics(
    clean_text: str,
    clean_lines: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    if not isinstance(clean_text, str):
        raise ValueError("extract_other_topics 需要 clean_text 字符串输入。")

    lines = _prepare_lines(clean_text=clean_text, clean_lines=clean_lines)
    if not lines:
        return {topic_name: {"found": False, "text": ""} for topic_name in OTHER_TOPIC_ORDER}

    topics: dict[str, dict[str, Any]] = {}
    for topic_name in OTHER_TOPIC_ORDER:
        if topic_name in MANUFACTURER_GROUP_TOPICS:
            topics[topic_name] = _extract_manufacturer_topic(lines)
        else:
            topics[topic_name] = _extract_single_line_topic(lines, OTHER_TOPIC_PATTERNS[topic_name])
    return topics


def _prepare_lines(clean_text: str, clean_lines: list[str] | None) -> list[str]:
    source_lines = clean_lines if isinstance(clean_lines, list) else clean_text.splitlines()
    prepared: list[str] = []

    for line in source_lines:
        normalized = SPACE_RE.sub(" ", str(line or "")).strip()
        if normalized:
            prepared.append(normalized)

    return prepared


def _extract_single_line_topic(lines: list[str], pattern: re.Pattern[str]) -> dict[str, Any]:
    for line in lines:
        if _is_noise_line(line):
            continue
        if pattern.search(line):
            text = _normalize_text(line)
            return {"found": bool(text), "text": text}
    return {"found": False, "text": ""}


def _extract_manufacturer_topic(lines: list[str]) -> dict[str, Any]:
    fragments: list[str] = []
    started = False

    for line in lines:
        if _is_noise_line(line):
            if started:
                break
            continue
        if MANUFACTURER_LINE_RE.search(line):
            fragments.append(_normalize_text(line))
            started = True
            continue
        if started:
            break

    text = _join_fragments(fragments, separator=" ")
    return {"found": bool(text), "text": text}


def _trim_ingredient_fragment(text: str) -> tuple[str, str]:
    normalized = _normalize_text(text)
    if not normalized:
        return "", ""

    end_match = INGREDIENT_END_RE.search(normalized)
    if end_match:
        return _normalize_text(normalized[: end_match.start()]), _normalize_anchor(end_match.group("anchor"))

    return normalized, ""


def _ingredient_boundary_anchor(line: str) -> str:
    if _is_noise_line(line):
        return ""

    match = INGREDIENT_BOUNDARY_RE.search(line)
    if match:
        return _normalize_anchor(match.group("anchor"))
    return ""


def _join_fragments(fragments: list[str], separator: str) -> str:
    non_empty = [fragment for fragment in fragments if fragment]
    if not non_empty:
        return ""
    return _normalize_text(separator.join(non_empty))


def _normalize_text(text: str) -> str:
    normalized = SPACE_RE.sub(" ", text).strip()
    normalized = TOPIC_TRIM_EDGE_RE.sub("", normalized)
    return normalized.strip()


def _normalize_anchor(anchor: str) -> str:
    return SPACE_RE.sub("", anchor).strip()


def _is_noise_line(line: str) -> bool:
    return bool(NOISE_LINE_RE.fullmatch(line.strip()))


__all__ = ["extract_ingredient_topic", "extract_other_topics"]
