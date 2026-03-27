from __future__ import annotations

import asyncio
import importlib
import io
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from starlette.datastructures import UploadFile

from app.core.error_handlers import register_exception_handlers
from app.core.errors import (
    FileTooLargeError,
    InvalidFileTypeError,
    TooManyConcurrentTasksError,
)
from app.models.analysis_task import AnalysisTask, TaskStatus
from app.models.report import Report
from app.models.user import User
from app.schemas.analysis_data import SUPPORTED_HEALTH_ADVICE_GROUPS
from app.workers.ocr_worker import OCRParallelResult, OCRTextResult, TableRecognitionResult
from tests.conftest import load_required_env


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalar_one(self):
        return self._value


class _ScalarsResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return SimpleNamespace(all=lambda: self._items)


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), color=(255, 0, 0)).save(buffer, format="PNG")
    return buffer.getvalue()


def _upload_file(filename: str, payload: bytes) -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(payload))


def _build_analysis_app(monkeypatch: pytest.MonkeyPatch):
    load_required_env(monkeypatch)
    api_module = importlib.reload(importlib.import_module("app.api.v1.analysis"))
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(api_module.router)
    return app, api_module


def _health_advice_payload() -> list[dict[str, str]]:
    return [
        {
            "group": group,
            "risk": "warning",
            "advice": f"{group} should limit this product and monitor sodium intake carefully every week.",
            "hint": "Limit intake",
        }
        for group in sorted(SUPPORTED_HEALTH_ADVICE_GROUPS)
    ]


def test_validate_file_accepts_png_and_rejects_invalid_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_required_env(monkeypatch)
    task_service_module = importlib.reload(
        importlib.import_module("app.services.task_service")
    )

    payload, content_type = asyncio.run(
        task_service_module.validate_file(_upload_file("tiny.png", _png_bytes()))
    )
    assert content_type == "image/png"
    assert payload.startswith(b"\x89PNG")

    with pytest.raises(InvalidFileTypeError):
        asyncio.run(
            task_service_module.validate_file(_upload_file("bad.png", b"not-an-image"))
        )


def test_validate_file_rejects_large_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)
    task_service_module = importlib.reload(
        importlib.import_module("app.services.task_service")
    )
    oversized = b"x" * ((10 * 1024 * 1024) + 1)

    with pytest.raises(FileTooLargeError):
        asyncio.run(
            task_service_module.validate_file(_upload_file("big.png", oversized))
        )


def test_check_concurrent_limit_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)
    task_service_module = importlib.reload(
        importlib.import_module("app.services.task_service")
    )
    fake_db = AsyncMock()
    fake_db.execute = AsyncMock(return_value=_ScalarResult(3))

    with pytest.raises(TooManyConcurrentTasksError):
        asyncio.run(task_service_module.check_concurrent_limit(uuid.uuid4(), fake_db))


def test_get_task_status_payload_includes_report_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_required_env(monkeypatch)
    task_service_module = importlib.reload(
        importlib.import_module("app.services.task_service")
    )
    task = AnalysisTask(
        user_id=uuid.uuid4(),
        image_key="uploads/u/test.png",
        image_url="https://example.com/image.png",
        status=TaskStatus.COMPLETED,
    )
    task.id = uuid.uuid4()
    task.created_at = datetime.now(timezone.utc)
    task.completed_at = datetime.now(timezone.utc)
    report = Report(
        task_id=task.id,
        user_id=task.user_id,
        score=90,
        llm_output_json={},
        nutrition_parse_source="ocr_text",
    )
    report.id = uuid.uuid4()
    task.report = report

    payload = asyncio.run(
        task_service_module.get_task_status_payload(task, AsyncMock())
    )

    assert payload.report_id == report.id
    assert payload.nutrition_parse_source == "ocr_text"
    assert payload.progress_message == "分析完成"


def test_analysis_upload_route_success(monkeypatch: pytest.MonkeyPatch) -> None:
    app, api_module = _build_analysis_app(monkeypatch)
    fake_db = AsyncMock()
    current_user = User(
        email="user@example.com",
        password_hash="hashed",
        is_verified=True,
        is_active=True,
    )
    current_user.id = uuid.uuid4()
    fake_task = SimpleNamespace(
        id=uuid.uuid4(),
        status=SimpleNamespace(value="pending"),
        created_at=datetime.now(timezone.utc),
    )
    storage = SimpleNamespace(
        upload_image=AsyncMock(
            return_value=("uploads/key.png", "https://example.com/key.png")
        ),
        delete_image=AsyncMock(),
    )

    async def override_db():
        yield fake_db

    async def override_user():
        return current_user

    app.dependency_overrides[api_module.get_db] = override_db
    app.dependency_overrides[api_module.get_current_user] = override_user
    monkeypatch.setattr(
        api_module, "validate_file", AsyncMock(return_value=(b"img", "image/png"))
    )
    monkeypatch.setattr(api_module, "check_concurrent_limit", AsyncMock())
    monkeypatch.setattr(api_module, "get_storage_service", lambda: storage)
    monkeypatch.setattr(api_module, "create_task", AsyncMock(return_value=fake_task))
    monkeypatch.setattr(api_module, "update_celery_task_id", AsyncMock())
    monkeypatch.setattr(
        api_module.celery_app,
        "send_task",
        lambda *args, **kwargs: SimpleNamespace(id="celery-1"),
    )

    with TestClient(app) as client:
        response = client.post(
            "/upload",
            files={"file": ("tiny.png", _png_bytes(), "image/png")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["task_id"] == str(fake_task.id)
    assert payload["data"]["status"] == "queued"


def test_analysis_upload_route_rolls_back_when_enqueue_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, api_module = _build_analysis_app(monkeypatch)
    fake_db = AsyncMock()
    fake_db.rollback = AsyncMock()
    current_user = User(
        email="user@example.com",
        password_hash="hashed",
        is_verified=True,
        is_active=True,
    )
    current_user.id = uuid.uuid4()
    fake_task = SimpleNamespace(
        id=uuid.uuid4(),
        status=SimpleNamespace(value="pending"),
        created_at=datetime.now(timezone.utc),
    )
    storage = SimpleNamespace(
        upload_image=AsyncMock(
            return_value=("uploads/key.png", "https://example.com/key.png")
        ),
        delete_image=AsyncMock(),
    )

    async def override_db():
        yield fake_db

    async def override_user():
        return current_user

    app.dependency_overrides[api_module.get_db] = override_db
    app.dependency_overrides[api_module.get_current_user] = override_user
    monkeypatch.setattr(
        api_module, "validate_file", AsyncMock(return_value=(b"img", "image/png"))
    )
    monkeypatch.setattr(api_module, "check_concurrent_limit", AsyncMock())
    monkeypatch.setattr(api_module, "get_storage_service", lambda: storage)
    monkeypatch.setattr(api_module, "create_task", AsyncMock(return_value=fake_task))
    monkeypatch.setattr(
        api_module.celery_app,
        "send_task",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("broker down")),
    )

    with TestClient(app) as client:
        response = client.post(
            "/upload",
            files={"file": ("tiny.png", _png_bytes(), "image/png")},
        )

    assert response.status_code == 503
    fake_db.rollback.assert_not_awaited()
    storage.delete_image.assert_awaited_once_with("uploads/key.png")


def test_process_image_task_marks_failed_for_not_implemented(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_required_env(monkeypatch)
    analysis_task_module = importlib.reload(
        importlib.import_module("app.tasks.analysis_task")
    )
    statuses: list[tuple[TaskStatus, str | None]] = []

    def fake_update(
        task_id: str, status: TaskStatus, error_message: str | None = None
    ) -> None:
        statuses.append((status, error_message))

    monkeypatch.setattr(analysis_task_module, "_update_task_status", fake_update)
    monkeypatch.setattr(
        analysis_task_module, "_download_image", lambda image_key: b"img"
    )
    monkeypatch.setattr(
        analysis_task_module.yolo_worker,
        "detect",
        lambda image_bytes: (_ for _ in ()).throw(NotImplementedError("yolo missing")),
    )
    analysis_task_module.process_image_task.push_request(id="celery-1", retries=0)
    try:
        result = analysis_task_module.process_image_task.run(
            "task-id", "image-key", str(uuid.uuid4())
        )
    finally:
        analysis_task_module.process_image_task.pop_request()

    assert result["status"] == "failed"
    assert statuses[0][0] == TaskStatus.PROCESSING
    assert statuses[-1][0] == TaskStatus.FAILED


def test_process_image_task_retries_retryable_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_required_env(monkeypatch)
    analysis_task_module = importlib.reload(
        importlib.import_module("app.tasks.analysis_task")
    )
    statuses: list[tuple[TaskStatus, str | None]] = []

    class RetryTriggered(Exception):
        pass

    def fake_update(
        task_id: str, status: TaskStatus, error_message: str | None = None
    ) -> None:
        statuses.append((status, error_message))

    def fake_retry(*, exc: Exception, countdown: int) -> None:
        raise RetryTriggered()

    monkeypatch.setattr(analysis_task_module, "_update_task_status", fake_update)
    monkeypatch.setattr(
        analysis_task_module,
        "_download_image",
        lambda image_key: (_ for _ in ()).throw(
            analysis_task_module.StorageServiceError("storage down")
        ),
    )
    monkeypatch.setattr(analysis_task_module.process_image_task, "retry", fake_retry)
    analysis_task_module.process_image_task.push_request(id="celery-1", retries=0)
    try:
        with pytest.raises(RetryTriggered):
            analysis_task_module.process_image_task.run(
                "task-id", "image-key", str(uuid.uuid4())
            )
    finally:
        analysis_task_module.process_image_task.pop_request()

    assert statuses == [(TaskStatus.PROCESSING, None)]


def test_process_image_task_completes_with_report_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_required_env(monkeypatch)
    analysis_task_module = importlib.reload(
        importlib.import_module("app.tasks.analysis_task")
    )
    completions: list[dict[str, object]] = []

    monkeypatch.setattr(
        analysis_task_module, "_update_task_status", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        analysis_task_module, "_download_image", lambda image_key: b"img"
    )
    monkeypatch.setattr(
        analysis_task_module.yolo_worker, "detect", lambda image_bytes: None
    )
    monkeypatch.setattr(
        analysis_task_module.ocr_worker,
        "recognize_full_text",
        lambda image_bytes: OCRTextResult(
            raw_text="salt, sugar",
            lines=[{"text": "salt, sugar"}],
            blocks=[],
            artifact_json_url="https://example.com/ocr.json",
        ),
    )
    monkeypatch.setattr(
        analysis_task_module.ocr_worker,
        "recognize_parallel",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not run")),
    )
    monkeypatch.setattr(
        analysis_task_module.nutrition_extractor,
        "parse",
        lambda table_result, ocr_fallback_text=None: {
            "items": [],
            "parse_method": "ocr_text",
        },
    )
    monkeypatch.setattr(
        analysis_task_module.ingredient_extractor,
        "extract",
        lambda full_raw_text: (["salt", "sugar"], "salt, sugar"),
    )
    monkeypatch.setattr(
        analysis_task_module.rag_worker,
        "retrieve_all",
        lambda ingredient_terms, ingredients_text: {
            "source_file": "chromadb",
            "ingredients_text": ingredients_text,
            "items_total": 0,
            "retrieval_results": [],
        },
    )
    monkeypatch.setattr(
        analysis_task_module.llm_worker,
        "analyze",
        lambda other_ocr_raw_text, nutrition_json, rag_results_json: {
            "score": 88,
            "summary": "S" * 60,
            "top_risks": ["salt"],
            "ingredients": [],
            "health_advice": _health_advice_payload(),
        },
    )

    def fake_complete(**kwargs):
        completions.append(kwargs)

    monkeypatch.setattr(
        analysis_task_module, "_complete_task_with_report", fake_complete
    )
    analysis_task_module.process_image_task.push_request(id="celery-1", retries=0)
    try:
        result = analysis_task_module.process_image_task.run(
            "task-id", "image-key", str(uuid.uuid4())
        )
    finally:
        analysis_task_module.process_image_task.pop_request()

    assert result["status"] == "completed"
    assert completions[0]["score"] == 88
    assert completions[0]["nutrition_json"]["parse_method"] == "ocr_text"
    assert completions[0]["artifact_urls"] == {
        "ocr_full_json_url": "https://example.com/ocr.json"
    }


def test_process_image_task_runs_parallel_ocr_when_yolo_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_required_env(monkeypatch)
    analysis_task_module = importlib.reload(
        importlib.import_module("app.tasks.analysis_task")
    )
    completions: list[dict[str, object]] = []
    parallel_inputs: list[tuple[bytes, bytes]] = []

    monkeypatch.setattr(
        analysis_task_module, "_update_task_status", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        analysis_task_module, "_download_image", lambda image_key: b"img"
    )
    monkeypatch.setattr(
        analysis_task_module.yolo_worker,
        "detect",
        lambda image_bytes: {"x1": 1, "y1": 2, "x2": 3, "y2": 4, "confidence": 0.9},
    )
    monkeypatch.setattr(
        analysis_task_module.yolo_worker,
        "crop_image",
        lambda image_bytes, bbox: b"cropped-img",
    )
    monkeypatch.setattr(
        analysis_task_module.yolo_worker,
        "mask_image",
        lambda image_bytes, bbox: b"masked-img",
    )
    monkeypatch.setattr(
        analysis_task_module.ocr_worker,
        "recognize_parallel",
        lambda full_text_image_bytes, nutrition_image_bytes=None: (
            parallel_inputs.append((full_text_image_bytes, nutrition_image_bytes))
            or OCRParallelResult(
                full_text=OCRTextResult(
                    raw_text="salt, sugar",
                    lines=[{"text": "salt, sugar"}],
                    blocks=[],
                    artifact_json_url="https://example.com/ocr.json",
                ),
                nutrition_table=TableRecognitionResult(
                    table_json={"table": [{"name": "energy", "value": "120", "unit": "kJ"}]},
                    ocr_fallback_text="energy 120kJ 2%",
                ),
            )
        ),
    )
    monkeypatch.setattr(
        analysis_task_module.ocr_worker,
        "recognize_full_text",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not run")),
    )
    monkeypatch.setattr(
        analysis_task_module.nutrition_extractor,
        "parse",
        lambda table_result, ocr_fallback_text=None: {
            "items": [],
            "parse_method": "table_recognition",
        },
    )
    monkeypatch.setattr(
        analysis_task_module.ingredient_extractor,
        "extract",
        lambda full_raw_text: (["salt", "sugar"], "salt, sugar"),
    )
    monkeypatch.setattr(
        analysis_task_module.rag_worker,
        "retrieve_all",
        lambda ingredient_terms, ingredients_text: {
            "source_file": "chromadb",
            "ingredients_text": ingredients_text,
            "items_total": 0,
            "retrieval_results": [],
        },
    )
    monkeypatch.setattr(
        analysis_task_module.llm_worker,
        "analyze",
        lambda other_ocr_raw_text, nutrition_json, rag_results_json: {
            "score": 88,
            "summary": "S" * 60,
            "top_risks": ["salt"],
            "ingredients": [],
            "health_advice": _health_advice_payload(),
        },
    )

    monkeypatch.setattr(
        analysis_task_module, "_complete_task_with_report", lambda **kwargs: completions.append(kwargs)
    )
    analysis_task_module.process_image_task.push_request(id="celery-1", retries=0)
    try:
        result = analysis_task_module.process_image_task.run(
            "task-id", "image-key", str(uuid.uuid4())
        )
    finally:
        analysis_task_module.process_image_task.pop_request()

    assert result["status"] == "completed"
    assert parallel_inputs == [(b"masked-img", b"cropped-img")]
    assert completions[0]["nutrition_json"]["parse_method"] == "table_recognition"
