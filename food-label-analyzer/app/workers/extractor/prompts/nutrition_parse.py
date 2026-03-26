from __future__ import annotations


def build_nutrition_parse_prompt() -> str:
    return """你是营养成分表解析助手。只返回合法 JSON，不要输出任何解释文字。

请从下面的 OCR 文本中提取营养成分表，并严格返回如下 JSON 结构：
{
  "items": [
    {
      "name": "能量",
      "value": "1234",
      "unit": "kJ",
      "daily_reference_percent": "15%"
    }
  ],
  "serving_size": "每100g"
}

规则：
1. name 必须是中文营养素名称。
2. value 保持数字字符串，不要附带单位。
3. unit 只能使用 kJ、kcal、g、mg、μg。
4. daily_reference_percent 若原文未提供则返回 null。
5. 如果无法可靠识别营养成分表，请返回 {"items": [], "serving_size": null}。

OCR 文本：
{nutrition_raw_text}
"""


__all__ = ["build_nutrition_parse_prompt"]
