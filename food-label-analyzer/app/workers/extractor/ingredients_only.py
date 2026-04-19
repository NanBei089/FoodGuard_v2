from __future__ import annotations

from typing import Any

from app.workers.extractor.rule_config import (
    INGREDIENT_CATEGORY_WRAPPER_RE,
    INGREDIENT_END_RE,
    INGREDIENT_INNER_SPLIT_TRIGGER_RE,
    INGREDIENT_LABEL_RE,
    INGREDIENT_LATEX_REPLACEMENTS,
    INGREDIENT_MEASURE_SUFFIX_RE,
    INGREDIENT_MERGE_PREFIX_TOKENS,
    INGREDIENT_NOISE_CHAR_RE,
    INGREDIENT_NOISE_EDGE_RE,
    INGREDIENT_PAREN_MEASURE_SUFFIX_RE,
    INGREDIENT_SINGLE_CHAR_KEEP_SET,
    INGREDIENT_TOP_LEVEL_DELIMITERS,
    INGREDIENT_VALID_TERM_RE,
    INGREDIENT_WRAPPED_TOKEN_RE,
    INLINE_INGREDIENT_LABEL_RE,
    SPACE_RE,
)

"""仅配料输出构造器，用于把配料主题转换成标准 items 列表。"""


def build_ingredients_output(
    ingredient_topic: dict[str, Any],
    roi_id: str,
    input_json: str,
) -> dict[str, Any]:
    """构造配料提取结果。"""
    raw_text = str(ingredient_topic.get("text") or "")
    trace_meta = (
        ingredient_topic.get("trace", {}) if isinstance(ingredient_topic, dict) else {}
    )
    prepared = _prepare_ingredient_segment(raw_text)
    ingredient_text = prepared["text"]
    found = bool(ingredient_topic.get("found")) and bool(ingredient_text)

    items = (
        [{"term": term} for term in _split_ingredient_terms(ingredient_text)]
        if found
        else []
    )

    return {
        "roi_id": roi_id,
        "found": bool(items) if found else False,
        "source": {
            "input_json": input_json,
        },
        "ingredients_text": ingredient_text if found else "",
        "items": items,
        "notes": [],
        "trace": {
            "start_anchor": prepared["start_anchor"]
            or str(trace_meta.get("start_anchor") or ""),
            "end_anchor": prepared["end_anchor"]
            or str(trace_meta.get("end_anchor") or ""),
        },
    }


def _split_ingredient_terms(text: str) -> list[str]:
    """拆分并清洗配料项。"""
    segment = _prepare_ingredient_segment(text)["text"]
    if not segment:
        return []

    top_level_tokens = _merge_fragmented_tokens(_split_top_level(segment))
    terms: list[str] = []
    seen: set[str] = set()

    for token in top_level_tokens:
        for term in _expand_token(token):
            if not term or term in seen:
                continue
            seen.add(term)
            terms.append(term)

    if not terms:
        fallback = _normalize_simple_term(segment)
        if fallback:
            terms.append(fallback)

    return terms


def _prepare_ingredient_segment(text: str) -> dict[str, str]:
    """裁剪配料片段中的起止锚点和噪声。"""
    segment = str(text or "").strip()
    start_anchor = ""
    end_anchor = ""
    if not segment:
        return {"text": "", "start_anchor": "", "end_anchor": ""}

    inline_matches = list(INLINE_INGREDIENT_LABEL_RE.finditer(segment))
    if inline_matches:
        last_match = inline_matches[-1]
        start_anchor = _normalize_anchor(last_match.group("anchor"))
        segment = segment[last_match.end() :]
    else:
        leading_match = INGREDIENT_LABEL_RE.match(segment)
        if leading_match:
            start_anchor = _normalize_anchor(leading_match.group("anchor"))
            segment = segment[leading_match.end() :]

    end_match = INGREDIENT_END_RE.search(segment)
    if end_match:
        end_anchor = _normalize_anchor(end_match.group("anchor"))
        segment = segment[: end_match.start()]

    cleaned = _normalize_ingredient_text(segment)
    return {
        "text": cleaned,
        "start_anchor": start_anchor,
        "end_anchor": end_anchor,
    }


def _expand_token(token: str) -> list[str]:
    """展开单个配料 token，处理复合配料括号结构。"""
    normalized = _normalize_simple_term(token, keep_spaces=True)
    if not normalized:
        return []

    wrapped_match = INGREDIENT_WRAPPED_TOKEN_RE.match(normalized)
    if not wrapped_match:
        term = _normalize_simple_term(normalized)
        return [term] if term else []

    outer = _normalize_simple_term(wrapped_match.group("outer"))
    inner = wrapped_match.group("inner")

    if INGREDIENT_CATEGORY_WRAPPER_RE.fullmatch(outer):
        # “食品添加剂（A、B）”这类外层只是分类名，真正配料在括号内。
        nested_terms: list[str] = []
        for nested in _merge_fragmented_tokens(_split_top_level(inner)):
            nested_term = _normalize_simple_term(nested)
            if nested_term:
                nested_terms.append(nested_term)
        return nested_terms

    results: list[str] = []
    if outer:
        results.append(outer)

    if INGREDIENT_INNER_SPLIT_TRIGGER_RE.search(inner):
        for nested in _merge_fragmented_tokens(_split_top_level(inner)):
            nested_term = _normalize_simple_term(nested)
            if nested_term and nested_term not in results:
                results.append(nested_term)

    return results


def _merge_fragmented_tokens(tokens: list[str]) -> list[str]:
    """修复 OCR 把“单/双”等前缀拆开的情况。"""
    merged: list[str] = []
    index = 0

    while index < len(tokens):
        current = _coerce_merge_token(tokens[index])
        if (
            current in INGREDIENT_MERGE_PREFIX_TOKENS
            and index + 1 < len(tokens)
            and (next_token := _coerce_merge_token(tokens[index + 1]))
            and next_token[:1] in INGREDIENT_MERGE_PREFIX_TOKENS
        ):
            merged.append(f"{current}、{next_token}")
            index += 2
            continue

        merged.append(tokens[index])
        index += 1

    return merged


def _split_top_level(text: str) -> list[str]:
    """按括号外的顶层分隔符拆分配料。"""
    tokens: list[str] = []
    buffer: list[str] = []
    depth = 0

    for char in text:
        if char in "（(":
            depth += 1
            buffer.append(char)
            continue
        if char in "）)":
            depth = max(0, depth - 1)
            buffer.append(char)
            continue
        if char in INGREDIENT_TOP_LEVEL_DELIMITERS and depth == 0:
            token = "".join(buffer).strip()
            if token:
                tokens.append(token)
            buffer = []
            continue
        buffer.append(char)

    tail = "".join(buffer).strip()
    if tail:
        tokens.append(tail)

    return tokens


def _coerce_merge_token(token: str) -> str:
    """把 token 归一化为用于前缀合并判断的形式。"""
    return _normalize_ingredient_text(token).replace(" ", "")


def _normalize_simple_term(token: str, keep_spaces: bool = False) -> str:
    """清洗并校验单个配料名。"""
    normalized = _normalize_ingredient_text(token, keep_spaces=keep_spaces)
    normalized = INGREDIENT_PAREN_MEASURE_SUFFIX_RE.sub("", normalized)
    normalized = INGREDIENT_MEASURE_SUFFIX_RE.sub("", normalized)
    normalized = INGREDIENT_NOISE_EDGE_RE.sub("", normalized)
    normalized = normalized.strip()

    if not normalized:
        return ""
    if not keep_spaces:
        normalized = normalized.replace(" ", "")
    if len(normalized) == 1 and normalized not in INGREDIENT_SINGLE_CHAR_KEEP_SET:
        return ""
    if not INGREDIENT_VALID_TERM_RE.search(normalized):
        return ""
    return normalized


def _normalize_ingredient_text(text: str, keep_spaces: bool = True) -> str:
    """执行配料文本通用归一化。"""
    normalized = str(text or "")
    for source, target in INGREDIENT_LATEX_REPLACEMENTS:
        normalized = normalized.replace(source, target)
    normalized = INGREDIENT_NOISE_CHAR_RE.sub("", normalized)
    normalized = INGREDIENT_NOISE_EDGE_RE.sub("", normalized)
    normalized = SPACE_RE.sub(" " if keep_spaces else "", normalized).strip()
    normalized = INGREDIENT_NOISE_EDGE_RE.sub("", normalized)
    return normalized.strip()


def _normalize_anchor(anchor: str) -> str:
    """归一化配料主题锚点。"""
    return SPACE_RE.sub("", str(anchor or "")).strip()


__all__ = ["build_ingredients_output"]
