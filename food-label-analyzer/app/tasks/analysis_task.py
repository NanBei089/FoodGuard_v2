from __future__ import annotations

import uuid
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

import structlog
from celery.exceptions import SoftTimeLimitExceeded
from minio import Minio
from pydantic import ValidationError
from sqlalchemy import select

from app.core.config import get_settings
from app.core.errors import (
    EmbeddingServiceError,
    LLMServiceError,
    OCRServiceError,
    StorageServiceError,
)
from app.db.session import get_sync_db
from app.models.analysis_task import AnalysisTask, TaskStatus
from app.models.report import Report
from app.schemas.analysis_data import FoodHealthAnalysisOutput, NutritionData, RAGResults
from app.tasks.celery_app import celery_app
from app.workers import llm_worker, ocr_worker, rag_worker, yolo_worker
from app.workers.extractor import ingredient_extractor, nutrition_extractor
from app.workers.ocr_worker import OCRTextResult, TableRecognitionResult


logger = structlog.get_logger(__name__)


def _to_plain_data(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, (dict, list, str, int, float, bool)):
        return value
    if hasattr(value, "__dict__"):
        return {key: item for key, item in vars(value).items() if not key.startswith("_")}
    return value


def _extract_score(llm_output_json: dict[str, Any]) -> int:
    raw_score = llm_output_json.get("score", 0)
    try:
        score = int(raw_score)
    except (TypeError, ValueError):
        score = 0
    return max(0, min(100, score))


def _validate_optional_json(model_cls, payload: dict[str, Any] | None, field_name: str) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return payload
    try:
        return model_cls.model_validate(payload).model_dump()
    except ValidationError as exc:
        logger.warning(
            "report_json_validation_skipped",
            field_name=field_name,
            validation_errors=exc.errors(),
        )
        return payload


def _build_artifact_urls(
    full_text_result: OCRTextResult,
    table_result: TableRecognitionResult | None,
) -> dict[str, str] | None:
    artifact_urls: dict[str, str] = {}
    if full_text_result.artifact_json_url:
        artifact_urls["ocr_full_json_url"] = full_text_result.artifact_json_url
    if table_result and table_result.table_html_url:
        artifact_urls["table_html_url"] = table_result.table_html_url
    if table_result and table_result.table_xlsx_url:
        artifact_urls["table_xlsx_url"] = table_result.table_xlsx_url
    return artifact_urls or None


def _download_image(image_key: str) -> bytes:
    settings = get_settings()
    client = Minio(
        endpoint=settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY.get_secret_value(),
        secure=settings.MINIO_USE_SSL,
    )
    response = None
    try:
        response = client.get_object(settings.MINIO_BUCKET_NAME, image_key)
        return response.read()
    except Exception as exc:
        raise StorageServiceError("Failed to download source image") from exc
    finally:
        if response is not None:
            response.close()
            response.release_conn()


def _update_task_status(task_id: str, status: TaskStatus, error_message: str | None = None) -> None:
    task_uuid = uuid.UUID(task_id)
    with get_sync_db() as db:
        task = db.get(AnalysisTask, task_uuid)
        if task is None:
            return
        task.status = status
        task.error_message = error_message
        if status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            task.completed_at = datetime.now(timezone.utc)
        elif status == TaskStatus.PROCESSING:
            task.completed_at = None


def _complete_task_with_report(
    task_id: str,
    user_id: str,
    ingredients_text: str,
    nutrition_json: dict[str, Any] | None,
    rag_results_json: dict[str, Any] | None,
    llm_output_json: dict[str, Any],
    score: int,
    artifact_urls: dict[str, Any] | None = None,
) -> None:
    task_uuid = uuid.UUID(task_id)
    user_uuid = uuid.UUID(user_id)
    validated_llm_output = FoodHealthAnalysisOutput.model_validate(llm_output_json).model_dump()
    validated_nutrition = _validate_optional_json(NutritionData, nutrition_json, "nutrition_json")
    validated_rag_results = _validate_optional_json(RAGResults, rag_results_json, "rag_results_json")
    parse_source = None
    nutrition_source_payload = validated_nutrition if isinstance(validated_nutrition, dict) else nutrition_json
    if isinstance(nutrition_source_payload, dict):
        raw_parse_source = nutrition_source_payload.get("parse_method")
        parse_source = str(raw_parse_source) if isinstance(raw_parse_source, str) else None

    with get_sync_db() as db:
        task = db.get(AnalysisTask, task_uuid)
        if task is None:
            return

        result = db.execute(select(Report).where(Report.task_id == task_uuid))
        report = result.scalar_one_or_none()
        if report is None:
            report = Report(task_id=task_uuid, user_id=user_uuid, score=score, llm_output_json=validated_llm_output)
            db.add(report)

        report.ingredients_text = ingredients_text
        report.nutrition_json = validated_nutrition
        report.nutrition_parse_source = parse_source
        report.rag_results_json = validated_rag_results
        report.llm_output_json = validated_llm_output
        report.score = score
        report.artifact_urls = artifact_urls

        task.status = TaskStatus.COMPLETED
        task.error_message = None
        task.completed_at = datetime.now(timezone.utc)


def _run_ocr_full_text(image_bytes: bytes) -> OCRTextResult:
    try:
        return ocr_worker.recognize_full_text(image_bytes)
    except NotImplementedError:
        raise
    except Exception as exc:
        raise OCRServiceError("OCR full-text recognition failed") from exc


def _run_ocr_table(image_bytes: bytes) -> TableRecognitionResult:
    try:
        return ocr_worker.recognize_nutrition_table(image_bytes)
    except NotImplementedError:
        raise
    except Exception as exc:
        raise OCRServiceError("Nutrition table recognition failed") from exc


def _run_rag(ingredient_terms: list[str], ingredients_text: str) -> dict[str, Any]:
    try:
        return rag_worker.retrieve_all(ingredient_terms, ingredients_text)
    except NotImplementedError:
        raise
    except Exception as exc:
        raise EmbeddingServiceError("RAG retrieval failed") from exc


def _run_llm(full_text: str, nutrition_json: dict[str, Any], rag_results_json: dict[str, Any]) -> dict[str, Any]:
    try:
        return llm_worker.analyze(full_text, nutrition_json, rag_results_json)
    except NotImplementedError:
        raise
    except Exception as exc:
        raise LLMServiceError("LLM analysis failed") from exc


@celery_app.task(
    bind=True,
    name="analysis.process_image",
    max_retries=2,
    soft_time_limit=270,
    time_limit=300,
)
def process_image_task(self, task_id: str, image_key: str, user_id: str) -> dict[str, Any]:
    started_at = perf_counter()
    logger.info(
        "analysis_task_started",
        task_id=task_id,
        image_key=image_key,
        user_id=user_id,
        celery_task_id=self.request.id,
    )
    _update_task_status(task_id, TaskStatus.PROCESSING)
    timings: dict[str, int] = {}

    try:
        step_started = perf_counter()
        image_bytes = _download_image(image_key)
        timings["download_ms"] = int((perf_counter() - step_started) * 1000)

        step_started = perf_counter()
        bbox = yolo_worker.detect(image_bytes)
        cropped_image = yolo_worker.crop_image(image_bytes, bbox) if bbox else image_bytes
        timings["yolo_ms"] = int((perf_counter() - step_started) * 1000)

        step_started = perf_counter()
        full_text_result = _run_ocr_full_text(image_bytes)
        full_text = full_text_result.raw_text
        table_result = _run_ocr_table(cropped_image) if bbox else None
        timings["ocr_ms"] = int((perf_counter() - step_started) * 1000)

        step_started = perf_counter()
        nutrition_output = nutrition_extractor.parse(
            table_result.model_dump() if table_result else None,
            table_result.ocr_fallback_text if table_result and table_result.ocr_fallback_text else full_text or None,
        )
        nutrition_json = _to_plain_data(nutrition_output) or {}
        if not isinstance(nutrition_json, dict):
            nutrition_json = {}
        timings["nutrition_ms"] = int((perf_counter() - step_started) * 1000)

        step_started = perf_counter()
        ingredient_terms, ingredients_text = ingredient_extractor.extract(full_text)
        timings["ingredients_ms"] = int((perf_counter() - step_started) * 1000)

        step_started = perf_counter()
        rag_output = _run_rag(ingredient_terms, ingredients_text)
        rag_results_json = _to_plain_data(rag_output) or {}
        if not isinstance(rag_results_json, dict):
            rag_results_json = {}
        timings["rag_ms"] = int((perf_counter() - step_started) * 1000)

        step_started = perf_counter()
        llm_output = _run_llm(full_text, nutrition_json, rag_results_json)
        llm_output_json = _to_plain_data(llm_output) or {}
        if not isinstance(llm_output_json, dict):
            llm_output_json = {}
        score = _extract_score(llm_output_json)
        timings["llm_ms"] = int((perf_counter() - step_started) * 1000)

        _complete_task_with_report(
            task_id=task_id,
            user_id=user_id,
            ingredients_text=ingredients_text,
            nutrition_json=nutrition_json,
            rag_results_json=rag_results_json,
            llm_output_json=llm_output_json,
            score=score,
            artifact_urls=_build_artifact_urls(full_text_result, table_result),
        )
        total_elapsed_ms = int((perf_counter() - started_at) * 1000)
        logger.info("analysis_task_completed", task_id=task_id, total_elapsed_ms=total_elapsed_ms, timings=timings)
        return {
            "task_id": task_id,
            "status": TaskStatus.COMPLETED.value,
            "total_elapsed_ms": total_elapsed_ms,
        }
    except SoftTimeLimitExceeded:
        error_message = "Analysis timeout"
        _update_task_status(task_id, TaskStatus.FAILED, error_message)
        logger.warning("analysis_task_timeout", task_id=task_id, timings=timings)
        return {"task_id": task_id, "status": TaskStatus.FAILED.value}
    except (OCRServiceError, LLMServiceError, StorageServiceError, EmbeddingServiceError) as exc:
        if self.request.retries < self.max_retries:
            logger.warning(
                "analysis_task_retrying",
                task_id=task_id,
                retries=self.request.retries,
                exception_type=exc.__class__.__name__,
                exception_message=str(exc),
            )
            raise self.retry(exc=exc, countdown=10)
        _update_task_status(task_id, TaskStatus.FAILED, str(exc))
        logger.warning(
            "analysis_task_failed_after_retries",
            task_id=task_id,
            exception_type=exc.__class__.__name__,
            exception_message=str(exc),
        )
        return {"task_id": task_id, "status": TaskStatus.FAILED.value}
    except NotImplementedError as exc:
        _update_task_status(task_id, TaskStatus.FAILED, str(exc))
        logger.warning("analysis_task_not_implemented", task_id=task_id, error_message=str(exc))
        return {"task_id": task_id, "status": TaskStatus.FAILED.value}
    except Exception as exc:
        _update_task_status(task_id, TaskStatus.FAILED, str(exc))
        logger.error(
            "analysis_task_failed",
            task_id=task_id,
            exception_type=exc.__class__.__name__,
            exception_message=str(exc),
            exc_info=exc,
        )
        return {"task_id": task_id, "status": TaskStatus.FAILED.value}


__all__ = ["process_image_task"]
