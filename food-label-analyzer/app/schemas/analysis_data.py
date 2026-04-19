from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

"""分析流水线内部和报告落库使用的结构化数据 schema。"""

IngredientRisk = Literal["safe", "warning", "danger"]
HealthAdviceGroup = Literal["儿童", "孕妇", "老年人", "过敏人群", "一般成年人"]
NutritionParseMethod = Literal[
    "table_recognition", "ocr_text", "llm_fallback", "empty", "failed"
]

SUPPORTED_HEALTH_ADVICE_GROUPS = {
    "儿童",
    "孕妇",
    "老年人",
    "过敏人群",
    "一般成年人",
}


class _AnalysisDataSchema(BaseModel):
    """分析数据 schema 的公共基类。"""

    model_config = ConfigDict(from_attributes=True)


class NutritionItem(_AnalysisDataSchema):
    """单个营养成分项。"""

    name: str
    value: str
    unit: str
    daily_reference_percent: str | None = None
    level: Literal["good", "neutral", "attention", "warning"] | None = None
    recommendation: str | None = Field(default=None, min_length=4, max_length=60)


class NutritionData(_AnalysisDataSchema):
    """营养成分表结构化结果。"""

    items: list[NutritionItem] = Field(default_factory=list)
    serving_size: str | None = None
    advice_summary: str | None = Field(default=None, min_length=10, max_length=200)
    parse_method: NutritionParseMethod = "empty"


class RAGMatch(_AnalysisDataSchema):
    """单条 RAG 命中结果。"""

    id: str
    term: str
    normalized_term: str
    aliases: list[str] = Field(default_factory=list)
    function_category: str
    is_primary: bool
    similarity_score: float = Field(ge=0, le=1)


class RAGRetrievalItem(_AnalysisDataSchema):
    """单个配料词的 RAG 检索结果。"""

    raw_term: str
    normalized_term: str
    retrieved: bool
    match_quality: Literal["high", "weak", "empty"]
    matches: list[RAGMatch] = Field(default_factory=list)


class RAGResults(_AnalysisDataSchema):
    """整份配料表的 RAG 检索汇总。"""

    source_file: str = "chromadb"
    ingredients_text: str = ""
    items_total: int = 0
    retrieval_results: list[RAGRetrievalItem] = Field(default_factory=list)


class IngredientItem(_AnalysisDataSchema):
    """LLM 输出的配料风险分析项。"""

    name: str
    risk: IngredientRisk
    description: str = Field(min_length=10, max_length=120)
    function_category: str | None = None
    rules: list[str] = Field(default_factory=list)


class HealthAdviceItem(_AnalysisDataSchema):
    """面向特定人群的健康建议。"""

    group: HealthAdviceGroup
    risk: IngredientRisk
    advice: str = Field(min_length=30, max_length=120)
    hint: str = Field(min_length=5, max_length=50)


class HazardItem(_AnalysisDataSchema):
    """核心风险点。"""

    level: Literal["high", "medium", "low"] = Field(description="风险等级")
    desc: str = Field(description="风险描述", min_length=5, max_length=100)


class FoodHealthAnalysisOutput(_AnalysisDataSchema):
    """LLM 最终健康分析输出。"""

    score: int = Field(ge=0, le=100)
    summary: str = Field(min_length=30, max_length=200)
    nutrition_advice: str | None = Field(default=None, min_length=20, max_length=200)
    hazards: list[HazardItem] = Field(default_factory=list, max_length=5)
    benefits: list[str] = Field(default_factory=list, max_length=5)
    ingredients: list[IngredientItem]
    health_advice: list[HealthAdviceItem] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def validate_health_advice_groups(self) -> FoodHealthAnalysisOutput:
        """确保每个支持人群都恰好有一条建议。"""
        groups = [item.group for item in self.health_advice]
        if (
            len(groups) != len(SUPPORTED_HEALTH_ADVICE_GROUPS)
            or set(groups) != SUPPORTED_HEALTH_ADVICE_GROUPS
        ):
            raise ValueError(
                "health_advice must contain exactly one item for each supported group",
            )
        return self


__all__ = [
    "FoodHealthAnalysisOutput",
    "HealthAdviceGroup",
    "HealthAdviceItem",
    "HazardItem",
    "IngredientItem",
    "IngredientRisk",
    "NutritionData",
    "NutritionItem",
    "NutritionParseMethod",
    "RAGMatch",
    "RAGResults",
    "RAGRetrievalItem",
    "SUPPORTED_HEALTH_ADVICE_GROUPS",
]
