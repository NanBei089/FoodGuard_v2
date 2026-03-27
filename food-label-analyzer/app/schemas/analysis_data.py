from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    model_config = ConfigDict(from_attributes=True)


class NutritionItem(_AnalysisDataSchema):
    name: str
    value: str
    unit: str
    daily_reference_percent: str | None = None
    level: Literal["good", "neutral", "attention", "warning"] | None = None
    recommendation: str | None = Field(default=None, min_length=4, max_length=60)


class NutritionData(_AnalysisDataSchema):
    items: list[NutritionItem] = Field(default_factory=list)
    serving_size: str | None = None
    advice_summary: str | None = Field(default=None, min_length=10, max_length=200)
    parse_method: NutritionParseMethod = "empty"


class RAGMatch(_AnalysisDataSchema):
    id: str
    term: str
    normalized_term: str
    aliases: list[str] = Field(default_factory=list)
    function_category: str
    is_primary: bool
    similarity_score: float = Field(ge=0, le=1)


class RAGRetrievalItem(_AnalysisDataSchema):
    raw_term: str
    normalized_term: str
    retrieved: bool
    match_quality: Literal["high", "weak", "empty"]
    matches: list[RAGMatch] = Field(default_factory=list)


class RAGResults(_AnalysisDataSchema):
    source_file: str = "chromadb"
    ingredients_text: str = ""
    items_total: int = 0
    retrieval_results: list[RAGRetrievalItem] = Field(default_factory=list)


class IngredientItem(_AnalysisDataSchema):
    name: str
    risk: IngredientRisk
    description: str = Field(min_length=10, max_length=120)
    function_category: str | None = None
    rules: list[str] = Field(default_factory=list)


class HealthAdviceItem(_AnalysisDataSchema):
    group: HealthAdviceGroup
    risk: IngredientRisk
    advice: str = Field(min_length=30, max_length=120)
    hint: str = Field(min_length=5, max_length=50)


class HazardItem(_AnalysisDataSchema):
    level: Literal["high", "medium", "low"] = Field(description="风险等级")
    desc: str = Field(description="风险描述", min_length=5, max_length=100)


class FoodHealthAnalysisOutput(_AnalysisDataSchema):
    score: int = Field(ge=0, le=100)
    summary: str = Field(min_length=30, max_length=200)
    nutrition_advice: str | None = Field(default=None, min_length=20, max_length=200)
    hazards: list[HazardItem] = Field(default_factory=list, max_length=5)
    benefits: list[str] = Field(default_factory=list, max_length=5)
    ingredients: list[IngredientItem]
    health_advice: list[HealthAdviceItem] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def validate_health_advice_groups(self) -> FoodHealthAnalysisOutput:
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
