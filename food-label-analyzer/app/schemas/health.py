from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import BASE_MODEL_CONFIG


ServiceState = Literal["up", "down"]
HealthStatus = Literal["healthy", "degraded"]


class _HealthSchema(BaseModel):
    model_config = BASE_MODEL_CONFIG


class HealthServicesSchema(_HealthSchema):
    database: ServiceState = Field(description="Database connectivity status", examples=["up"])
    redis: ServiceState = Field(description="Redis connectivity status", examples=["up"])
    minio: ServiceState = Field(description="MinIO connectivity status", examples=["up"])
    yolo_model: ServiceState = Field(description="YOLO model availability", examples=["up"])
    chromadb: ServiceState = Field(description="ChromaDB collection availability", examples=["up"])
    ollama_embedding: ServiceState = Field(description="Ollama embedding service availability", examples=["up"])
    ocr_runtime: ServiceState = Field(description="OCR runtime connectivity", examples=["up"])


class HealthCheckResponse(_HealthSchema):
    status: HealthStatus = Field(description="Overall health status", examples=["healthy"])
    timestamp: datetime = Field(description="Health check timestamp", examples=["2026-03-25T12:30:00Z"])
    version: str = Field(description="Application version", examples=["1.0.0"])
    services: HealthServicesSchema = Field(description="Per-service status")


__all__ = ["HealthCheckResponse", "HealthServicesSchema", "HealthStatus", "ServiceState"]
