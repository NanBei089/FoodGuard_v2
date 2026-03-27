from __future__ import annotations


def build_nutrition_table_llm_parse_prompt() -> str:
    return """You are a nutrition facts table normalization assistant.

Your task is to convert OCR output from a nutrition facts table into frontend-ready structured JSON.
Return valid JSON only. Do not return markdown, comments, explanations, or extra prose.

Return this exact JSON shape:
{
  "items": [
    {
      "name": "Energy",
      "value": "55",
      "unit": "kJ",
      "daily_reference_percent": "1%",
      "level": "neutral",
      "recommendation": "Amount is low"
    }
  ],
  "serving_size": "Per serving (2.5g)",
  "advice_summary": "Overall amounts are low, suitable for small-portion use."
}

Rules:
1. Keep every nutrient row that can be reliably extracted. Do not use a fixed whitelist to drop rows.
2. `name` is the frontend display name. If the OCR item name is obviously garbled or a typo of a standard nutrient name, correct it using table context, row order, unit, bilingual label, and nearby rows.
3. If you are not confident that a name is an OCR typo, keep the original OCR name instead of inventing a correction.
4. Preserve special or uncommon nutrient items when they are present. Unknown items must not be discarded just because they are uncommon.
5. `value` must contain only the numeric part as a string.
6. `unit` must be one of: `kJ`, `kcal`, `g`, `mg`, `ug`. Convert equivalent OCR variants like `μg`, `mcg`, `微克` to `ug`.
7. `daily_reference_percent` should be a string like `1%`. If not available, return `null`.
8. `level` must be one of: `good`, `neutral`, `attention`, `warning`.
9. `recommendation` should be a short Chinese suggestion for that row, about 4 to 30 Chinese characters.
10. `advice_summary` should be a short Chinese summary for the whole table, about 20 to 120 Chinese characters.
11. Prefer `table_result_json` as the primary source. Use `nutrition_raw_text` only to repair OCR mistakes or fill small gaps.
12. If the nutrition table cannot be extracted reliably, return:
{
  "items": [],
  "serving_size": null,
  "advice_summary": null
}

OCR table structure:
{table_result_json}

OCR fallback text:
{nutrition_raw_text}
"""


__all__ = ["build_nutrition_table_llm_parse_prompt"]
