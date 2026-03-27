from __future__ import annotations

import re
from typing import Any

LINEBREAK_RE = re.compile(r"\r\n?|\u2028|\u2029")
CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200f\u2060\ufeff]")
BROKEN_CHAR_RE = re.compile(r"�")
DECOR_SYMBOL_RE = re.compile(r"[●•·◆★■□▲▼※▪◦◇◎○◆◇★☆]+")
HTML_TAG_RE = re.compile(r"<[^>]+>")
MARKDOWN_HEADER_RE = re.compile(r"^\s*#+\s*")
MULTI_SPACE_RE = re.compile(r"[ \t\f\v]+")
MULTI_BLANK_LINE_RE = re.compile(r"\n{3,}")
CANONICAL_SPACE_RE = re.compile(r"\s+")
CANONICAL_PUNCT_RE = re.compile(r"[：:；;，,。.!！?？、\-\(\)（）\[\]{}<>《》\"']+")
FORCED_ANCHOR_RE = re.compile(
    r"(配\s*料\s*表|配\s*料|原\s*料|成\s*分|贮\s*存\s*条\s*件|保\s*存\s*方\s*法|"
    r"保\s*质\s*期|生\s*产\s*日\s*期|生\s*产\s*日|食\s*品\s*生\s*产\s*许\s*可\s*证|"
    r"生\s*产\s*许\s*可\s*证|执\s*行\s*标\s*准|产\s*品\s*标\s*准\s*代\s*号|"
    r"产\s*地|生\s*产\s*商|制\s*造\s*商|委\s*托\s*方|受\s*委\s*托\s*方|厂\s*址|地\s*址|"
    r"电\s*话|联\s*系\s*方\s*式|服\s*务\s*热\s*线|净\s*含\s*量|净\s*重|规\s*格|"
    r"食\s*用\s*方\s*法|SC\s*\d+)",
    re.IGNORECASE,
)
MERGE_VALUE_PREFIX_RE = re.compile(
    r"^(地\s*址|厂\s*址|生\s*产\s*商|制\s*造\s*商|委\s*托\s*方|受\s*委\s*托\s*方)",
    re.IGNORECASE,
)
TERMINAL_PUNCT_RE = re.compile(r"[。！？!?；;]$")
LICENSE_NUMBER_RE = re.compile(r"^SC\s*\d+$", re.IGNORECASE)
SINGLE_CHAR_KEEP_SET = {"盐", "糖", "油", "水", "醋", "茶"}


def clean_ocr_text(raw_text: str, lines: list[Any] | None = None) -> dict[str, Any]:
    if not isinstance(raw_text, str) or not raw_text.strip():
        raise ValueError("输入 JSON 缺少有效 raw_text 文本。")

    line_texts = _collect_line_texts(raw_text=raw_text, lines=lines)
    normalized_lines = [_normalize_line(text) for text in line_texts]
    filtered_lines = [text for text in normalized_lines if text]
    deduped_lines = _dedupe_adjacent_lines(filtered_lines)
    merged_lines = _merge_broken_lines(deduped_lines)

    clean_text = "\n".join(merged_lines).strip()
    clean_text = MULTI_BLANK_LINE_RE.sub("\n\n", clean_text)
    clean_lines = [line for line in clean_text.splitlines() if line.strip()]
    flat_text = MULTI_SPACE_RE.sub(" ", clean_text.replace("\n", " ")).strip()

    return {
        "clean_text": clean_text,
        "flat_text": flat_text,
        "clean_lines": clean_lines,
    }


def _collect_line_texts(raw_text: str, lines: list[Any] | None) -> list[str]:
    if isinstance(lines, list):
        collected: list[str] = []
        for item in lines:
            if isinstance(item, dict):
                text = str(item.get("text") or "")
            else:
                text = str(item or "")
            if text.strip():
                collected.append(text)
        if collected:
            return collected

    normalized_raw = _normalize_basic(raw_text)
    return normalized_raw.split("\n")


def _normalize_line(text: str) -> str:
    normalized = _normalize_basic(text)
    normalized = MARKDOWN_HEADER_RE.sub("", normalized)
    normalized = MULTI_SPACE_RE.sub(" ", normalized)
    return normalized.strip()


def _normalize_basic(text: str) -> str:
    normalized = LINEBREAK_RE.sub("\n", text)
    normalized = CONTROL_CHAR_RE.sub(" ", normalized)
    normalized = ZERO_WIDTH_RE.sub("", normalized)
    normalized = BROKEN_CHAR_RE.sub(" ", normalized)
    normalized = DECOR_SYMBOL_RE.sub(" ", normalized)
    normalized = HTML_TAG_RE.sub(" ", normalized)
    normalized = normalized.replace("\u00a0", " ")
    return normalized


def _dedupe_adjacent_lines(lines: list[str]) -> list[str]:
    deduped: list[str] = []
    previous_canonical = ""

    for line in lines:
        canonical = _canonicalize_line(line)
        if canonical and canonical == previous_canonical:
            continue
        deduped.append(line)
        if canonical:
            previous_canonical = canonical

    return deduped


def _canonicalize_line(text: str) -> str:
    canonical = CANONICAL_SPACE_RE.sub("", text)
    canonical = CANONICAL_PUNCT_RE.sub("", canonical)
    return canonical.strip().lower()


def _merge_broken_lines(lines: list[str]) -> list[str]:
    merged: list[str] = []
    index = 0

    while index < len(lines):
        current = lines[index]
        next_index = index

        while next_index + 1 < len(lines) and _should_merge(
            current, lines[next_index + 1]
        ):
            current = f"{current}{lines[next_index + 1].lstrip()}"
            next_index += 1

        merged.append(MULTI_SPACE_RE.sub(" ", current).strip())
        index = next_index + 1

    return merged


def _should_merge(current: str, next_line: str) -> bool:
    current_compact = CANONICAL_SPACE_RE.sub("", current)
    next_compact = CANONICAL_SPACE_RE.sub("", next_line)

    if not next_compact:
        return False

    if len(current_compact) <= 1 and current_compact not in SINGLE_CHAR_KEEP_SET:
        return True

    current_anchor_match = bool(FORCED_ANCHOR_RE.search(current_compact))
    next_anchor_match = bool(FORCED_ANCHOR_RE.search(next_compact))
    combined = f"{current_compact}{next_compact}"

    if (
        FORCED_ANCHOR_RE.search(combined)
        and not current_anchor_match
        and not next_anchor_match
    ):
        return True

    if current.endswith((":", "：")):
        return True

    if LICENSE_NUMBER_RE.fullmatch(next_compact) and (
        "许可证" in current_compact
        or "SC" in current_compact
        or "编号" in current_compact
    ):
        return True

    if (
        MERGE_VALUE_PREFIX_RE.search(current)
        and not next_anchor_match
        and not TERMINAL_PUNCT_RE.search(current)
    ):
        return True

    return False


__all__ = ["clean_ocr_text"]
