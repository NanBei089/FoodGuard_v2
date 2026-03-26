from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.analysis_data import (
    HealthAdviceItem as HealthAdviceSchema,
    IngredientItem as IngredientAnalysisSchema,
    NutritionData as NutritionSchema,
    NutritionItem as NutritionItemSchema,
)
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
    top_risks: list[str] = Field(
        default_factory=list,
        description="Top identified risks",
        examples=[["High sodium", "Multiple sweeteners"]],
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


class ReportListItemSchema(_ReportSchema):
    report_id: UUID = Field(description="Report identifier")
    task_id: UUID = Field(description="Task identifier")
    score: int = Field(description="Overall health score", examples=[85])
    summary: str | None = Field(default=None, description="Overall analysis summary", examples=["Moderate risk"])
    image_url: str = Field(description="Signed image URL", examples=["https://minio.example.com/report.png"])
    created_at: datetime = Field(description="Report creation time", examples=["2026-03-25T12:30:00Z"])


class ReportListResponseSchema(PageResponse[ReportListItemSchema]):
    model_config = BASE_MODEL_CONFIG


class ReportDetailResponseSchema(_ReportSchema):
    report_id: UUID = Field(description="Report identifier")
    task_id: UUID = Field(description="Task identifier")
    image_url: str = Field(description="Signed image URL", examples=["https://minio.example.com/report.png"])
    ingredients_text: str | None = Field(
        default=None,
        description="OCR extracted raw ingredients text",
        examples=["Ingredients: water, sugar, salt, flavoring."],
    )
    nutrition: NutritionSchema | None = Field(default=None, description="Structured nutrition data")
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
    created_at: datetime = Field(description="Report creation time", examples=["2026-03-25T12:30:00Z"])


__all__ = [
    "AnalysisSchema",
    "HealthAdviceSchema",
    "IngredientAnalysisSchema",
    "NutritionItemSchema",
    "NutritionSchema",
    "RagSummarySchema",
    "ReportDetailResponseSchema",
    "ReportListItemSchema",
    "ReportListResponseSchema",
]
