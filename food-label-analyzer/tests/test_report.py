from __future__ import annotations

import asyncio
import importlib
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.error_handlers import register_exception_handlers
from app.core.errors import ReportNotFoundError
from app.models.analysis_task import AnalysisTask, TaskStatus
from app.models.report import Report
from app.models.user import User
from app.schemas.analysis_data import SUPPORTED_HEALTH_ADVICE_GROUPS
from tests.conftest import load_required_env


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value


class _RowsResult:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class _OneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def one_or_none(self):
        return self._value


def _build_report_app(monkeypatch: pytest.MonkeyPatch):
    load_required_env(monkeypatch)
    api_module = importlib.reload(importlib.import_module("app.api.v1.reports"))
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(api_module.router, prefix="/reports")
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


def test_report_service_builds_list_and_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)
    report_service_module = importlib.reload(
        importlib.import_module("app.services.report_service")
    )

    user_id = uuid.uuid4()
    task_id = uuid.uuid4()
    report_id = uuid.uuid4()
    created_at = datetime.now(timezone.utc)
    row = SimpleNamespace(
        report_id=report_id,
        task_id=task_id,
        score=85,
        llm_output_json={"summary": "S" * 60},
        created_at=created_at,
        image_key="uploads/u/report.png",
        image_url="https://example.com/original.png",
    )

    report = Report(
        task_id=task_id,
        user_id=user_id,
        ingredients_text="salt, sugar",
        nutrition_json={
            "items": [
                {
                    "name": "能量",
                    "value": "1330",
                    "unit": "kJ",
                    "daily_reference_percent": "16%",
                    "level": "attention",
                    "recommendation": "注意控制单次食用量",
                },
                {
                    "name": "蛋白质",
                    "value": "12.6",
                    "unit": "g",
                    "daily_reference_percent": "21%",
                    "level": "good",
                    "recommendation": "可作为补充来源",
                },
                {
                    "name": "钠",
                    "value": "509",
                    "unit": "mg",
                    "daily_reference_percent": "25%",
                    "level": "warning",
                    "recommendation": "钠偏高需重点控制",
                },
            ],
            "serving_size": "每100克",
            "advice_summary": "该食品钠偏高，蛋白质尚可，建议控制单次食用量并避免与高盐食品同食。",
            "parse_method": "ocr_text",
        },
        nutrition_parse_source="ocr_text",
        rag_results_json={
            "source_file": "chromadb",
            "ingredients_text": "salt, sugar",
            "items_total": 2,
            "retrieval_results": [
                {
                    "raw_term": "salt",
                    "normalized_term": "salt",
                    "retrieved": True,
                    "match_quality": "high",
                    "matches": [],
                },
                {
                    "raw_term": "sugar",
                    "normalized_term": "sugar",
                    "retrieved": False,
                    "match_quality": "empty",
                    "matches": [],
                },
            ],
        },
        llm_output_json={
            "summary": "S" * 60,
            "top_risks": ["salt"],
            "ingredients": [
                {
                    "name": "salt",
                    "risk": "warning",
                    "description": "Salt may increase sodium load for sensitive adults.",
                    "function_category": "seasoning",
                    "rules": [],
                }
            ],
            "health_advice": _health_advice_payload(),
            "score": 85,
        },
        score=85,
        artifact_urls={"ocr_full_json_url": "https://example.com/ocr.json"},
    )
    report.id = report_id
    report.created_at = created_at

    fake_storage = SimpleNamespace(
        get_presigned_url=AsyncMock(return_value="https://example.com/signed.png")
    )
    monkeypatch.setattr(
        report_service_module, "get_storage_service", lambda: fake_storage
    )

    fake_db = AsyncMock()
    fake_db.execute = AsyncMock(
        side_effect=[
            _ScalarResult(1),
            _RowsResult([row]),
            _OneOrNoneResult((report, row.image_key, row.image_url)),
        ]
    )

    report_list = asyncio.run(
        report_service_module.get_report_list(user_id, 5, 10, fake_db)
    )
    detail = asyncio.run(
        report_service_module.get_report_detail(report.id, user_id, fake_db)
    )

    assert report_list.total == 1
    assert report_list.page == 1
    assert report_list.total_pages == 1
    assert report_list.items[0].summary == "S" * 60
    assert report_list.items[0].image_url == "https://example.com/signed.png"
    assert detail.nutrition_parse_source == "ocr_text"
    assert detail.nutrition is not None
    assert detail.nutrition_table is not None
    assert detail.nutrition_table.serving_basis == "每100克 (Per 100g)"
    assert len(detail.nutrition_table.rows) == 3
    assert detail.nutrition_table.rows[0].display_name == "能量 / Energy"
    assert detail.nutrition_table.rows[1].level == "good"
    assert detail.nutrition_table.rows[2].recommendation == "钠偏高需重点控制"
    assert (
        detail.nutrition_table.advice_summary
        == "该食品钠偏高，蛋白质尚可，建议控制单次食用量并避免与高盐食品同食。"
    )
    assert detail.analysis.summary == "S" * 60
    assert len(detail.analysis.ingredients) == 1
    assert len(detail.analysis.health_advice) == 5
    assert detail.rag_summary.total_ingredients == 2
    assert detail.rag_summary.retrieved_count == 1
    assert detail.rag_summary.high_match_count == 1
    assert detail.rag_summary.empty_count == 1
    assert detail.artifact_urls == {"ocr_full_json_url": "https://example.com/ocr.json"}


def test_report_service_sanitizes_legacy_html_polluted_ingredients_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_required_env(monkeypatch)
    report_service_module = importlib.reload(
        importlib.import_module("app.services.report_service")
    )

    user_id = uuid.uuid4()
    task_id = uuid.uuid4()
    report_id = uuid.uuid4()
    created_at = datetime.now(timezone.utc)
    report = Report(
        task_id=task_id,
        user_id=user_id,
        ingredients_text=(
            "\u53ea\u6709\u897f\u6885 \u9ad8\u81b3\u98df\u7ea4\u7ef4</div>"
            "<table><tr><td>\u9879\u76ee</td><td>\u6bcf100\u514b</td></tr>"
            "<tr><td>\u78b3\u6c34\u5316\u5408\u7269</td><td>59.8\u514b</td></tr></table>"
            "\u4ea7\u54c1\u540d\u79f0\uff1a\u65e0\u6838\u5927\u897f\u6885\n"
            "\u4ea7\u54c1\u7c7b\u578b\uff1a\u6c34\u679c\u5e72\u5236\u54c1\n"
            "\u914d\u6599\u8868\uff1a\u897f\u6885100%"
        ),
        nutrition_json=None,
        nutrition_parse_source="table_recognition",
        rag_results_json=None,
        llm_output_json={
            "summary": "S" * 60,
            "top_risks": [],
            "ingredients": [],
            "health_advice": _health_advice_payload(),
            "score": 85,
        },
        score=85,
    )
    report.id = report_id
    report.created_at = created_at

    fake_db = AsyncMock()
    fake_db.execute = AsyncMock(
        return_value=_OneOrNoneResult((report, None, "https://example.com/original.png"))
    )

    detail = asyncio.run(
        report_service_module.get_report_detail(report.id, user_id, fake_db)
    )

    assert detail.ingredients_text == "\u897f\u6885100%"


def test_report_service_returns_empty_page_when_total_is_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_required_env(monkeypatch)
    report_service_module = importlib.reload(
        importlib.import_module("app.services.report_service")
    )

    fake_db = AsyncMock()
    fake_db.execute = AsyncMock(return_value=_ScalarResult(0))

    report_list = asyncio.run(
        report_service_module.get_report_list(uuid.uuid4(), 3, 10, fake_db)
    )

    assert report_list.total == 0
    assert report_list.items == []
    assert report_list.page == 1
    assert report_list.total_pages == 0


def test_report_service_raises_for_missing_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_required_env(monkeypatch)
    report_service_module = importlib.reload(
        importlib.import_module("app.services.report_service")
    )
    fake_db = AsyncMock()
    fake_db.execute = AsyncMock(return_value=_OneOrNoneResult(None))

    with pytest.raises(ReportNotFoundError):
        asyncio.run(
            report_service_module.get_report_detail(uuid.uuid4(), uuid.uuid4(), fake_db)
        )


def test_report_service_returns_empty_rag_summary_for_invalid_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_required_env(monkeypatch)
    report_service_module = importlib.reload(
        importlib.import_module("app.services.report_service")
    )

    summary = report_service_module._build_rag_summary(
        {"retrieval_results": [{"legacy": True}]}
    )

    assert summary.total_ingredients == 0
    assert summary.retrieved_count == 0
    assert summary.high_match_count == 0
    assert summary.weak_match_count == 0
    assert summary.empty_count == 0


def test_reports_router_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    app, api_module = _build_report_app(monkeypatch)
    schema_module = importlib.reload(importlib.import_module("app.schemas.report"))
    current_user = User(
        email="user@example.com",
        password_hash="hashed",
        is_verified=True,
        is_active=True,
    )
    current_user.id = uuid.uuid4()
    fake_db = AsyncMock()
    report_id = uuid.uuid4()

    async def override_db():
        yield fake_db

    async def override_user():
        return current_user

    async def fake_get_report_list(user_id, page, page_size, db):
        return schema_module.ReportListResponseSchema(
            items=[
                schema_module.ReportListItemSchema(
                    report_id=report_id,
                    task_id=uuid.uuid4(),
                    score=80,
                    summary="summary",
                    image_url="https://example.com/report.png",
                    created_at=datetime.now(timezone.utc),
                )
            ],
            total=1,
            page=page,
            page_size=page_size,
        )

    async def fake_get_report_detail(report_id_value, user_id, db):
        return schema_module.ReportDetailResponseSchema(
            report_id=report_id_value,
            task_id=uuid.uuid4(),
            image_url="https://example.com/report.png",
            ingredients_text="salt, sugar",
            nutrition=None,
            nutrition_parse_source="ocr_text",
            analysis=schema_module.AnalysisSchema(
                score=80,
                summary="summary",
                top_risks=["salt"],
                ingredients=[],
                health_advice=[],
            ),
            rag_summary=schema_module.RagSummarySchema(
                total_ingredients=2,
                retrieved_count=1,
                high_match_count=1,
                weak_match_count=0,
                empty_count=1,
            ),
            artifact_urls={"ocr_full_json_url": "https://example.com/ocr.json"},
            created_at=datetime.now(timezone.utc),
        )

    async def fake_delete_report(report_id_value, user_id, db) -> None:
        assert report_id_value == report_id

    app.dependency_overrides[api_module.get_db] = override_db
    app.dependency_overrides[api_module.get_current_user] = override_user
    monkeypatch.setattr(api_module, "get_report_list", fake_get_report_list)
    monkeypatch.setattr(api_module, "get_report_detail", fake_get_report_detail)
    monkeypatch.setattr(api_module, "delete_report", fake_delete_report)

    with TestClient(app) as client:
        list_response = client.get("/reports")
        detail_response = client.get(f"/reports/{report_id}")
        delete_response = client.delete(f"/reports/{report_id}")

    assert list_response.status_code == 200
    assert list_response.json()["data"]["items"][0]["report_id"] == str(report_id)
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()["data"]
    assert detail_payload["report_id"] == str(report_id)
    assert detail_payload["analysis"]["score"] == 80
    assert detail_payload["rag_summary"]["high_match_count"] == 1
    assert (
        detail_payload["artifact_urls"]["ocr_full_json_url"]
        == "https://example.com/ocr.json"
    )
    assert delete_response.status_code == 200
    assert delete_response.json() == {"code": 0, "message": "ok", "data": None}
