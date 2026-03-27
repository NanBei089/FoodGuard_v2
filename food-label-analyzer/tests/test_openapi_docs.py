from __future__ import annotations

import importlib

from tests.conftest import load_required_env


def test_openapi_routes_expose_summary_description_and_responses(monkeypatch) -> None:
    load_required_env(monkeypatch, SKIP_STARTUP_CHECKS="true")
    main_module = importlib.reload(importlib.import_module("app.main"))

    schema = main_module.app.openapi()
    report_detail = schema["paths"]["/api/v1/reports/{report_id}"]["get"]
    auth_login = schema["paths"]["/api/v1/auth/login"]["post"]
    analysis_upload = schema["paths"]["/api/v1/analysis/upload"]["post"]

    assert isinstance(report_detail.get("summary"), str) and report_detail["summary"]
    assert (
        isinstance(report_detail.get("description"), str)
        and report_detail["description"]
    )
    assert set(report_detail["responses"].keys()) >= {"200", "401", "404", "422"}

    assert isinstance(auth_login.get("summary"), str) and auth_login["summary"]
    assert isinstance(auth_login.get("description"), str) and auth_login["description"]
    assert set(auth_login["responses"].keys()) >= {"200", "401", "403", "422"}

    assert (
        isinstance(analysis_upload.get("summary"), str) and analysis_upload["summary"]
    )
    assert (
        isinstance(analysis_upload.get("description"), str)
        and analysis_upload["description"]
    )
    assert set(analysis_upload["responses"].keys()) >= {
        "200",
        "400",
        "401",
        "429",
        "503",
        "422",
    }


def test_openapi_schemas_expose_field_metadata_and_new_report_shape(
    monkeypatch,
) -> None:
    load_required_env(monkeypatch, SKIP_STARTUP_CHECKS="true")
    main_module = importlib.reload(importlib.import_module("app.main"))

    schema = main_module.app.openapi()
    report_detail_schema = schema["components"]["schemas"][
        "ApiResponse_ReportDetailResponseSchema_"
    ]
    auth_schema = schema["components"]["schemas"]["RegisterRequest"]
    analysis_schema = schema["components"]["schemas"]["ApiResponse_TaskStatusResponse_"]

    assert set(report_detail_schema["properties"].keys()) >= {"code", "message", "data"}

    assert auth_schema["properties"]["email"]["description"]
    assert auth_schema["properties"]["code"]["examples"] == ["123456"]
    assert set(analysis_schema["properties"].keys()) >= {"code", "message", "data"}


def test_docs_and_redoc_are_hidden_outside_development(monkeypatch) -> None:
    load_required_env(monkeypatch, SKIP_STARTUP_CHECKS="true", APP_ENV="production")
    main_module = importlib.reload(importlib.import_module("app.main"))

    assert main_module.app.docs_url is None
    assert main_module.app.redoc_url is None
