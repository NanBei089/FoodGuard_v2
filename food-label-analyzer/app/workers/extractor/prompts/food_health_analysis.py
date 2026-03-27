from __future__ import annotations

from app.schemas.analysis_data import (
    FoodHealthAnalysisOutput,
    HealthAdviceItem,
    IngredientItem,
)


def build_food_health_analysis_prompt() -> str:
    return """你是食品安全分析专家，精通中国食品法规（GB2760-2024 等）。
请根据食品标签 OCR 文本、营养成分数据和 RAG 检索结果，生成结构化的食品健康分析报告。

严格遵守以下 JSON 输出格式，禁止返回任何额外文字：
{{
  "score": 整数,
  "summary": "60-100字的总结",
  "hazards": [
    {{"level": "high|medium|low", "desc": "5-100字的风险描述，如：钠含量达到每日建议摄入量的 100%"}}
  ],
  "benefits": [
    "5-100字的优点描述，如：含有丰富的膳食纤维"
  ],
  "ingredients": [
    {{
      "name": "配料名称",
      "risk": "safe|warning|danger",
      "description": "22-60字的描述",
      "function_category": "功能分类",
      "rules": ["GB2760-2024"]
    }}
  ],
  "health_advice": [
    {{"group": "儿童", "risk": "safe|warning|danger", "advice": "60-80字建议", "hint": "10-22字提示"}},
    {{"group": "孕妇", "risk": "safe|warning|danger", "advice": "60-80字建议", "hint": "10-22字提示"}},
    {{"group": "老年人", "risk": "safe|warning|danger", "advice": "60-80字建议", "hint": "10-22字提示"}},
    {{"group": "过敏人群", "risk": "safe|warning|danger", "advice": "60-80字建议", "hint": "10-22字提示"}},
    {{"group": "一般成年人", "risk": "safe|warning|danger", "advice": "60-80字建议", "hint": "10-22字提示"}}
  ]
}}

食品标签 OCR 原文：
{other_ocr_raw_text}

营养成分表数据：
{nutrition_json}

配料 RAG 检索结果：
{rag_results_json}
"""


def build_food_health_analysis_repair_prompt() -> str:
    return """你是 JSON 修复助手。之前的输出没有通过格式校验，请只返回修正后的合法 JSON。

严格遵守以下 JSON 输出格式，禁止返回任何额外文字：
{{
  "score": 整数,
  "summary": "60-100字的总结",
  "hazards": [
    {{"level": "high|medium|low", "desc": "5-100字的风险描述"}}
  ],
  "benefits": [
    "5-100字的优点描述"
  ],
  "ingredients": [
    {{
      "name": "配料名称",
      "risk": "safe|warning|danger",
      "description": "22-60字的描述",
      "function_category": "功能分类",
      "rules": ["GB2760-2024"]
    }}
  ],
  "health_advice": [
    {{"group": "儿童", "risk": "safe|warning|danger", "advice": "60-80字建议", "hint": "10-22字提示"}},
    {{"group": "孕妇", "risk": "safe|warning|danger", "advice": "60-80字建议", "hint": "10-22字提示"}},
    {{"group": "老年人", "risk": "safe|warning|danger", "advice": "60-80字建议", "hint": "10-22字提示"}},
    {{"group": "过敏人群", "risk": "safe|warning|danger", "advice": "60-80字建议", "hint": "10-22字提示"}},
    {{"group": "一般成年人", "risk": "safe|warning|danger", "advice": "60-80字建议", "hint": "10-22字提示"}}
  ]
}}

上一次输出（格式错误，需修复）：
{previous_output_json}

校验错误：
{validation_errors}

原始 OCR 文本：
{other_ocr_raw_text}

原始营养成分数据：
{nutrition_json}

原始 RAG 检索结果：
{rag_results_json}
"""


__all__ = [
    "FoodHealthAnalysisOutput",
    "HealthAdviceItem",
    "IngredientItem",
    "build_food_health_analysis_prompt",
    "build_food_health_analysis_repair_prompt",
]
