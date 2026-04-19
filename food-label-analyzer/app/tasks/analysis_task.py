from __future__ import annotations

import re
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
from app.schemas.analysis_data import (
    FoodHealthAnalysisOutput,
    NutritionData,
    RAGResults,
)
from app.tasks.celery_app import celery_app
from app.workers import llm_worker, ocr_worker, rag_worker, yolo_worker
from app.workers.extractor import ingredient_extractor, nutrition_extractor
from app.workers.ocr_worker import OCRParallelResult, OCRTextResult, TableRecognitionResult

"""分析异步任务编排：下载图片、调用 YOLO/OCR/RAG/LLM，并落库为报告。"""

logger = structlog.get_logger(__name__)


def _to_plain_data(value: Any) -> Any:
    """把 Pydantic/对象实例尽量转成可序列化的普通数据结构。"""
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, (dict, list, str, int, float, bool)):
        return value
    if hasattr(value, "__dict__"):
        return {
            key: item for key, item in vars(value).items() if not key.startswith("_")
        }
    return value


def _extract_score(llm_output_json: dict[str, Any]) -> int:
    """从 LLM 输出中提取并裁剪健康分。"""
    raw_score = llm_output_json.get("score", 0)
    try:
        score = int(raw_score)
    except (TypeError, ValueError):
        score = 0
    return max(0, min(100, score))


def _validate_optional_json(
    model_cls, payload: dict[str, Any] | None, field_name: str
) -> dict[str, Any] | None:
    """对可选 JSON 字段做弱校验，避免单字段脏数据拖垮整条流水线。"""
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
    """汇总 OCR 产物链接，供报告详情页和调试使用。"""
    artifact_urls: dict[str, str] = {}
    if full_text_result.artifact_json_url:
        artifact_urls["ocr_full_json_url"] = full_text_result.artifact_json_url
    if table_result and table_result.table_html_url:
        artifact_urls["table_html_url"] = table_result.table_html_url
    if table_result and table_result.table_xlsx_url:
        artifact_urls["table_xlsx_url"] = table_result.table_xlsx_url
    return artifact_urls or None


def _download_image(image_key: str) -> bytes:
    """从 MinIO 下载任务原图。"""
    settings = get_settings()
    client = Minio(
        endpoint=settings.minio_client_endpoint,
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


def _update_task_status(
    task_id: str, status: TaskStatus, error_message: str | None = None
) -> None:
    """更新任务状态与完成时间。"""
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
    """把分析结果写回任务和报告表。"""
    task_uuid = uuid.UUID(task_id)
    user_uuid = uuid.UUID(user_id)
    validated_llm_output = FoodHealthAnalysisOutput.model_validate(
        llm_output_json
    ).model_dump()
    validated_nutrition = _validate_optional_json(
        NutritionData, nutrition_json, "nutrition_json"
    )
    validated_rag_results = _validate_optional_json(
        RAGResults, rag_results_json, "rag_results_json"
    )
    parse_source = None
    nutrition_source_payload = (
        validated_nutrition if isinstance(validated_nutrition, dict) else nutrition_json
    )
    if isinstance(nutrition_source_payload, dict):
        raw_parse_source = nutrition_source_payload.get("parse_method")
        parse_source = (
            str(raw_parse_source) if isinstance(raw_parse_source, str) else None
        )

    with get_sync_db() as db:
        task = db.get(AnalysisTask, task_uuid)
        if task is None:
            return

        result = db.execute(select(Report).where(Report.task_id == task_uuid))
        report = result.scalar_one_or_none()
        if report is None:
            report = Report(
                task_id=task_uuid,
                user_id=user_uuid,
                score=score,
                llm_output_json=validated_llm_output,
            )
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
    """执行整图 OCR，并统一转换为业务异常。"""
    try:
        return ocr_worker.recognize_full_text(image_bytes)
    except NotImplementedError:
        raise
    except Exception as exc:
        raise OCRServiceError("OCR full-text recognition failed") from exc


def _run_ocr_table(image_bytes: bytes) -> TableRecognitionResult:
    """执行营养表 OCR，并统一转换为业务异常。"""
    try:
        return ocr_worker.recognize_nutrition_table(image_bytes)
    except NotImplementedError:
        raise
    except Exception as exc:
        raise OCRServiceError("Nutrition table recognition failed") from exc


def _run_ocr_parallel(
    full_text_image_bytes: bytes,
    nutrition_image_bytes: bytes,
) -> OCRParallelResult:
    """并行执行整图 OCR 与营养表 OCR。"""
    try:
        return ocr_worker.recognize_parallel(
            full_text_image_bytes,
            nutrition_image_bytes=nutrition_image_bytes,
        )
    except NotImplementedError:
        raise
    except Exception as exc:
        raise OCRServiceError("Parallel OCR failed") from exc


def _extract_table_rows(table_result: TableRecognitionResult | None) -> list[list[str]]:
    """提取营养表的结构化行数据。"""
    if table_result is None or not isinstance(table_result.table_json, dict):
        return []

    raw_rows = table_result.table_json.get("rows")
    if not isinstance(raw_rows, list):
        return []

    rows: list[list[str]] = []
    for raw_row in raw_rows:
        if not isinstance(raw_row, list):
            continue
        row = [str(cell).strip() for cell in raw_row if str(cell).strip()]
        if row:
            rows.append(row)
    return rows


def _table_result_quality(table_result: TableRecognitionResult | None) -> tuple[int, int, int, int]:
    """评估营养表识别质量，用于比较不同 OCR 路径的结果。"""
    rows = _extract_table_rows(table_result)
    numeric_value_cells = sum(
        1
        for row in rows
        for cell in row[1:]
        if any(char.isdigit() for char in cell)
    )
    multi_column_rows = sum(1 for row in rows if len(row) >= 2)
    fallback_text_len = (
        len((table_result.ocr_fallback_text or "").strip()) if table_result else 0
    )
    return (
        numeric_value_cells,
        multi_column_rows,
        len(rows),
        fallback_text_len,
    )


def _table_result_is_incomplete(table_result: TableRecognitionResult | None) -> bool:
    """判断营养表识别结果是否明显不完整。"""
    numeric_value_cells, multi_column_rows, row_count, _ = _table_result_quality(
        table_result
    )
    if row_count == 0:
        return True
    if multi_column_rows == 0:
        return True
    if numeric_value_cells == 0:
        return True
    return False


def _choose_better_table_result(
    primary: TableRecognitionResult | None,
    candidate: TableRecognitionResult | None,
) -> TableRecognitionResult | None:
    """在两个营养表结果中选择质量更高的一份。"""
    primary_quality = _table_result_quality(primary)
    candidate_quality = _table_result_quality(candidate)
    if candidate_quality > primary_quality:
        return candidate
    return primary


def _run_rag(ingredient_terms: list[str], ingredients_text: str) -> dict[str, Any]:
    """执行配料 RAG 检索。"""
    try:
        return rag_worker.retrieve_all(ingredient_terms, ingredients_text)
    except NotImplementedError:
        raise
    except Exception as exc:
        raise EmbeddingServiceError("RAG retrieval failed") from exc


def _normalize_ingredient_term(term: str) -> str:
    """把配料名称归一化，便于去重与对齐。"""
    return re.sub(r"\s+", "", str(term or "").strip().lower())


def _dedupe_ingredient_terms(ingredient_terms: list[str]) -> list[str]:
    """按归一化结果去重，但保留原始展示文本。"""
    deduped: list[str] = []
    seen: set[str] = set()
    for term in ingredient_terms:
        normalized = _normalize_ingredient_term(term)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(str(term).strip())
    return deduped


def _build_rag_lookup(rag_results_json: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """把 RAG 检索结果转成按配料名索引的快速查找表。"""
    lookup: dict[str, dict[str, Any]] = {}
    retrieval_results = rag_results_json.get("retrieval_results")
    if not isinstance(retrieval_results, list):
        return lookup

    for item in retrieval_results:
        if not isinstance(item, dict):
            continue

        matches = item.get("matches")
        first_match = matches[0] if isinstance(matches, list) and matches else None
        function_category = None
        if isinstance(first_match, dict):
            raw_category = first_match.get("function_category")
            if isinstance(raw_category, str) and raw_category.strip():
                function_category = raw_category.strip()

        payload = {
            "function_category": function_category,
            "retrieved": bool(item.get("retrieved")),
        }
        for raw_key in (item.get("raw_term"), item.get("normalized_term")):
            normalized = _normalize_ingredient_term(str(raw_key or ""))
            if normalized and normalized not in lookup:
                lookup[normalized] = payload
    return lookup


def _infer_fallback_risk(term: str) -> str:
    """当 LLM 漏掉配料时，使用关键词规则给出保守风险等级。"""
    lowered = _normalize_ingredient_term(term)
    if any(keyword in lowered for keyword in ("氢化", "反式", "植脂末")):
        return "danger"
    if any(
        keyword in lowered
        for keyword in (
            "糖",
            "盐",
            "钠",
            "油",
            "脂",
            "黄油",
            "奶油",
            "香精",
            "香料",
            "色素",
            "防腐",
            "甜味剂",
            "乳化",
            "增稠",
        )
    ):
        return "warning"
    return "safe"


def _build_fallback_ingredient_item(
    term: str,
    rag_meta: dict[str, Any] | None,
) -> dict[str, Any]:
    """为缺失的配料补一条可展示的兜底分析项。"""
    function_category = None
    if isinstance(rag_meta, dict):
        raw_category = rag_meta.get("function_category")
        if isinstance(raw_category, str) and raw_category.strip():
            function_category = raw_category.strip()

    risk = _infer_fallback_risk(term)
    if risk == "danger":
        description = (
            f"识别到{term}，属于需要重点关注的加工配料，建议控制摄入频率并留意同类高负担成分叠加。"
        )
    elif risk == "warning":
        description = (
            f"识别到{term}，建议结合配料排序、食用量和整体营养负担综合判断，避免长期过量摄入。"
        )
    else:
        description = (
            f"识别到{term}，当前未见明确高风险信号，但仍建议结合整体配方和个人情况综合判断。"
        )

    return {
        "name": term,
        "risk": risk,
        "description": description,
        "function_category": function_category,
        "rules": [],
    }


def _ensure_ingredient_coverage(
    llm_output_json: dict[str, Any],
    ingredient_terms: list[str],
    rag_results_json: dict[str, Any],
) -> dict[str, Any]:
    """确保识别出的每个配料都能在最终报告里看到。"""
    if not isinstance(llm_output_json, dict):
        return {}

    expected_terms = _dedupe_ingredient_terms(ingredient_terms)
    if not expected_terms:
        return llm_output_json

    raw_items = llm_output_json.get("ingredients")
    current_items = raw_items if isinstance(raw_items, list) else []
    covered_terms: set[str] = set()
    normalized_items: list[dict[str, Any]] = []

    for item in current_items:
        if not isinstance(item, dict):
            continue
        raw_name = item.get("name")
        if not isinstance(raw_name, str) or not raw_name.strip():
            continue
        normalized = _normalize_ingredient_term(raw_name)
        if not normalized or normalized in covered_terms:
            continue
        covered_terms.add(normalized)
        normalized_items.append(item)

    rag_lookup = _build_rag_lookup(rag_results_json)
    for term in expected_terms:
        normalized = _normalize_ingredient_term(term)
        if normalized in covered_terms:
            continue
        # LLM 可能因为压缩总结而漏掉配料，这里补齐以保证报告对用户可追溯。
        normalized_items.append(
            _build_fallback_ingredient_item(term, rag_lookup.get(normalized))
        )
        covered_terms.add(normalized)

    llm_output_json["ingredients"] = normalized_items
    return llm_output_json


def _run_llm(
    full_text: str,
    nutrition_json: dict[str, Any],
    rag_results_json: dict[str, Any],
    ingredient_terms: list[str],
    ingredients_text: str,
) -> dict[str, Any]:
    """执行 LLM 分析，并兼容旧版 worker 的函数签名。"""
    try:
        return llm_worker.analyze(
            full_text,
            nutrition_json,
            rag_results_json,
            recognized_ingredient_terms=ingredient_terms,
            ingredients_text=ingredients_text,
        )
    except TypeError as exc:
        # 兼容尚未升级的新参数版本，避免注释任务影响用户当前未提交的实验改动。
        if (
            "recognized_ingredient_terms" not in str(exc)
            and "ingredients_text" not in str(exc)
        ):
            raise LLMServiceError("LLM analysis failed") from exc
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
def process_image_task(
    self, task_id: str, image_key: str, user_id: str
) -> dict[str, Any]:
    """执行整条食品标签分析流水线。

    Params:
        self: Celery task 实例。
        task_id: 分析任务 ID。
        image_key: 原图在对象存储中的键。
        user_id: 发起任务的用户 ID。

    Returns:
        dict[str, Any]: Celery 侧返回的任务结果摘要。
    """
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
        # 检出营养表后分别裁剪/打白，是为了让表格 OCR 与全文 OCR 互不干扰。
        cropped_image = (
            yolo_worker.crop_image(image_bytes, bbox) if bbox else image_bytes
        )
        masked_full_image = (
            yolo_worker.mask_image(image_bytes, bbox) if bbox else image_bytes
        )
        timings["yolo_ms"] = int((perf_counter() - step_started) * 1000)

        step_started = perf_counter()
        if bbox:
            parallel_result = _run_ocr_parallel(masked_full_image, cropped_image)
            full_text_result = parallel_result.full_text
            table_result = parallel_result.nutrition_table
            if _table_result_is_incomplete(table_result):
                try:
                    full_image_table_result = _run_ocr_table(image_bytes)
                except OCRServiceError as exc:
                    logger.warning(
                        "nutrition_table_full_image_fallback_failed",
                        task_id=task_id,
                        error_message=str(exc),
                    )
                else:
                    # 裁剪图通常更准，但一旦框偏了会漏行，所以再用整图结果做一次质量兜底。
                    selected_table_result = _choose_better_table_result(
                        table_result, full_image_table_result
                    )
                    if selected_table_result is not table_result:
                        logger.info(
                            "nutrition_table_full_image_fallback_selected",
                            task_id=task_id,
                            cropped_quality=_table_result_quality(table_result),
                            full_image_quality=_table_result_quality(
                                full_image_table_result
                            ),
                        )
                        table_result = selected_table_result
        else:
            full_text_result = _run_ocr_full_text(image_bytes)
            try:
                table_result = _run_ocr_table(image_bytes)
            except OCRServiceError as exc:
                logger.warning(
                    "nutrition_table_full_image_scan_failed",
                    task_id=task_id,
                    error_message=str(exc),
                )
                table_result = None
        full_text = full_text_result.raw_text
        timings["ocr_ms"] = int((perf_counter() - step_started) * 1000)

        step_started = perf_counter()
        nutrition_output = nutrition_extractor.parse(
            table_result.model_dump() if table_result else None,
            (
                table_result.ocr_fallback_text
                if table_result and table_result.ocr_fallback_text
                else full_text or None
            ),
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
        llm_output = _run_llm(
            full_text,
            nutrition_json,
            rag_results_json,
            ingredient_terms,
            ingredients_text,
        )
        llm_output_json = _to_plain_data(llm_output) or {}
        if not isinstance(llm_output_json, dict):
            llm_output_json = {}
        llm_output_json = _ensure_ingredient_coverage(
            llm_output_json,
            ingredient_terms,
            rag_results_json,
        )
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
        logger.info(
            "analysis_task_completed",
            task_id=task_id,
            total_elapsed_ms=total_elapsed_ms,
            timings=timings,
        )
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
    except (
        OCRServiceError,
        LLMServiceError,
        StorageServiceError,
        EmbeddingServiceError,
    ) as exc:
        if self.request.retries < self.max_retries:
            # OCR/LLM/存储等外部依赖具有瞬时失败特征，因此这里允许有限次重试。
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
        logger.warning(
            "analysis_task_not_implemented", task_id=task_id, error_message=str(exc)
        )
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
