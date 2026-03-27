from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.analysis_data import HealthAdviceItem as HealthAdviceSchema
from app.schemas.analysis_data import HazardItem as HazardSchema
from app.schemas.analysis_data import IngredientItem as IngredientAnalysisSchema
from app.schemas.analysis_data import NutritionData as NutritionSchema
from app.schemas.analysis_data import NutritionItem as NutritionItemSchema
from app.schemas.common import BASE_MODEL_CONFIG, PageResponse


class _ReportSchema(BaseModel):
    model_config = BASE_MODEL_CONFIG


class AnalysisSchema(_ReportSchema):
    score: int = Field(description="Overall health score", examples=[85])
    summary: str | None = Field(
        default=None,
        description="Overall analysis summary",
        examples=["Overall risk is moderate, driven by sodium and added sugar."],
    )
    hazards: list[HazardSchema] = Field(
        default_factory=list,
        description="Top identified risks with levels",
        examples=[[{"level": "high", "desc": "High sodium"}]],
    )
    benefits: list[str] = Field(
        default_factory=list,
        description="Identified health benefits",
        examples=[["Contains dietary fiber"]],
    )
    ingredients: list[IngredientAnalysisSchema] = Field(
        default_factory=list,
        description="Structured ingredient analysis",
    )
    health_advice: list[HealthAdviceSchema] = Field(
        default_factory=list,
        description="Advice for target populations",
    )


class RagSummarySchema(_ReportSchema):
    total_ingredients: int = Field(description="Total ingredient count", examples=[6])
    retrieved_count: int = Field(description="Ingredients matched in RAG", examples=[4])
    high_match_count: int = Field(description="High-confidence matches", examples=[3])
    weak_match_count: int = Field(description="Weak matches", examples=[1])
    empty_count: int = Field(description="Unmatched ingredients", examples=[2])


class NutritionTableRowSchema(_ReportSchema):
    nutrient_key: str = Field(description="Canonical nutrient key", examples=["sodium"])
    name_cn: str = Field(description="Chinese nutrient label", examples=["钠"])
    name_en: str | None = Field(
        default=None, description="English nutrient label", examples=["Sodium"]
    )
    display_name: str = Field(
        description="Display label for frontend", examples=["钠 / Sodium"]
    )
    amount: str = Field(description="Formatted amount", examples=["680 mg"])
    nrv_percent: float | None = Field(
        default=None, description="NRV percentage as number", examples=[68]
    )
    nrv_label: str | None = Field(
        default=None, description="Formatted NRV label", examples=["68%"]
    )
    recommendation: str = Field(
        description="Recommendation for this nutrient row",
        examples=["含量较高，需控制"],
    )
    level: Literal["good", "neutral", "attention", "warning"] = Field(
        description="Frontend style tone for this row"
    )
    is_child: bool = Field(
        default=False, description="Whether this row is a child nutrient item"
    )
    parent_key: str | None = Field(
        default=None,
        description="Parent nutrient key when this row is a child item",
        examples=["fat"],
    )


class NutritionTableSchema(_ReportSchema):
    title: str = Field(default="营养成分表", description="Section title")
    subtitle: str | None = Field(
        default=None,
        description="Section subtitle for serving basis",
        examples=["每100克 (Per 100g)"],
    )
    serving_basis: str | None = Field(
        default=None,
        description="Canonical serving basis label",
        examples=["每100克 (Per 100g)"],
    )
    parse_source: str | None = Field(
        default=None,
        description="Nutrition parsing source",
        examples=["table_recognition"],
    )
    rows: list[NutritionTableRowSchema] = Field(
        default_factory=list, description="Structured nutrition table rows"
    )
    advice_title: str = Field(default="营养师建议", description="Advice card title")
    advice_summary: str | None = Field(
        default=None,
        description="Summary advice for the whole table",
        examples=[
            "该食品钠含量不低，建议控制单次食用量，并避免与其他高盐食品叠加摄入。"
        ],
    )


class ReportListItemSchema(_ReportSchema):
    report_id: UUID = Field(description="Report identifier")
    task_id: UUID = Field(description="Task identifier")
    score: int = Field(description="Overall health score", examples=[85])
    summary: str | None = Field(
        default=None, description="Overall analysis summary", examples=["Moderate risk"]
    )
    image_url: str = Field(
        description="Signed image URL",
        examples=["https://minio.example.com/report.png"],
    )
    created_at: datetime = Field(
        description="Report creation time", examples=["2026-03-25T12:30:00Z"]
    )


class ReportListResponseSchema(PageResponse[ReportListItemSchema]):
    model_config = BASE_MODEL_CONFIG


class ReportDetailResponseSchema(_ReportSchema):
    report_id: UUID = Field(description="Report identifier")
    task_id: UUID = Field(description="Task identifier")
    image_url: str = Field(
        description="Signed image URL",
        examples=["https://minio.example.com/report.png"],
    )
    ingredients_text: str | None = Field(
        default=None,
        description="OCR extracted raw ingredients text",
        examples=["Ingredients: water, sugar, salt, flavoring."],
    )
    nutrition: dict[str, str] | None = Field(
        default=None, description="Formatted nutrition data (key-value pairs)"
    )
    nutrition_table: NutritionTableSchema | None = Field(
        default=None,
        description="Structured nutrition table payload for redesigned frontend",
    )
    nutrition_parse_source: str | None = Field(
        default=None,
        description="Nutrition parsing source",
        examples=["table_recognition", "ocr_text"],
    )
    analysis: AnalysisSchema = Field(description="Structured health analysis")
    rag_summary: RagSummarySchema = Field(description="RAG summary statistics")
    artifact_urls: dict[str, str] | None = Field(
        default=None,
        description="Generated artifact URLs",
        examples=[{"ocr_full_json_url": "https://minio.example.com/ocr.json"}],
    )
    created_at: datetime = Field(
        description="Report creation time", examples=["2026-03-25T12:30:00Z"]
    )


__all__ = [
    "AnalysisSchema",
    "HealthAdviceSchema",
    "HazardSchema",
    "IngredientAnalysisSchema",
    "NutritionTableRowSchema",
    "NutritionTableSchema",
    "NutritionItemSchema",
    "NutritionSchema",
    "RagSummarySchema",
    "ReportDetailResponseSchema",
    "ReportListItemSchema",
    "ReportListResponseSchema",
]
