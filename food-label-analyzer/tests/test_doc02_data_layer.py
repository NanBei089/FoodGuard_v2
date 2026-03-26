from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import runpy
import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import CreateIndex

from app.db.base import Base, CreatedAtMixin
from app.models.analysis_task import AnalysisTask, TaskStatus
from app.models.email_verification import EmailVerification, VerificationType
from app.models.password_reset import PasswordResetToken
from app.models.report import Report
from app.models.user import User
from app.schemas.analysis_data import FoodHealthAnalysisOutput, NutritionData, RAGResults
from tests.conftest import load_required_env


def test_doc02_metadata_and_mixins_register_expected_tables() -> None:
    expected_tables = {
        "users",
        "email_verifications",
        "password_reset_tokens",
        "analysis_tasks",
        "reports",
    }

    assert expected_tables.issubset(set(Base.metadata.tables))
    assert hasattr(CreatedAtMixin, "created_at")
    assert not hasattr(CreatedAtMixin, "updated_at")
    assert "gen_random_uuid" in str(User.__table__.c["id"].server_default.arg)


def test_user_and_task_models_define_expected_relationships_and_indexes() -> None:
    user_relationships = User.__mapper__.relationships
    task_relationships = AnalysisTask.__mapper__.relationships
    task_indexes = {index.name for index in AnalysisTask.__table__.indexes}

    user = User(
        id=uuid.uuid4(),
        email="user@example.com",
        password_hash="hashed-password",
    )

    assert set(user_relationships.keys()) == {"password_reset_tokens", "reports", "tasks"}
    assert set(task_relationships.keys()) == {"report", "user"}
    assert task_relationships["report"].uselist is False
    assert task_indexes == {
        "idx_analysis_tasks_created_at",
        "idx_analysis_tasks_status",
        "idx_analysis_tasks_user_id",
        "idx_analysis_tasks_user_status",
    }
    assert AnalysisTask.__table__.c["status"].type.enum_class is TaskStatus
    assert "created_at DESC" in str(
        CreateIndex(
            next(
                index
                for index in AnalysisTask.__table__.indexes
                if index.name == "idx_analysis_tasks_created_at"
            ),
        ).compile(dialect=postgresql.dialect()),
    )
    assert repr(user) == f"<User id={user.id} email={user.email}>"


def test_report_and_auth_related_models_define_expected_columns_constraints_and_indexes() -> None:
    email_indexes = {index.name for index in EmailVerification.__table__.indexes}
    reset_indexes = {index.name for index in PasswordResetToken.__table__.indexes}
    report_indexes = {index.name for index in Report.__table__.indexes}
    report_constraints = {constraint.name for constraint in Report.__table__.constraints}

    assert EmailVerification.__table__.c["type"].type.enum_class is VerificationType
    assert email_indexes == {
        "idx_email_verifications_email_type",
        "idx_email_verifications_expired_at",
    }
    assert reset_indexes == {
        "idx_password_reset_tokens_expired_at",
        "idx_password_reset_tokens_user_id",
    }
    assert list(PasswordResetToken.__table__.c["user_id"].foreign_keys)[0].ondelete == "CASCADE"
    assert isinstance(Report.__table__.c["nutrition_json"].type, JSONB)
    assert isinstance(Report.__table__.c["rag_results_json"].type, JSONB)
    assert isinstance(Report.__table__.c["llm_output_json"].type, JSONB)
    assert isinstance(Report.__table__.c["artifact_urls"].type, JSONB)
    assert report_constraints >= {"ck_reports_score_range"}
    assert report_indexes == {"idx_reports_score", "idx_reports_user_id_created_at"}
    assert "created_at DESC" in str(
        CreateIndex(
            next(
                index
                for index in Report.__table__.indexes
                if index.name == "idx_reports_user_id_created_at"
            ),
        ).compile(dialect=postgresql.dialect()),
    )


def test_analysis_data_schemas_validate_valid_payloads() -> None:
    nutrition = NutritionData.model_validate(
        {
            "items": [
                {
                    "name": "能量",
                    "value": "1500",
                    "unit": "kJ",
                    "daily_reference_percent": "18%",
                },
            ],
            "serving_size": "每100g",
            "parse_method": "table_recognition",
        },
    )
    rag_results = RAGResults.model_validate(
        {
            "source_file": "chromadb",
            "ingredients_text": "水、白砂糖、食用香精",
            "items_total": 2,
            "retrieval_results": [
                {
                    "raw_term": "食用香精",
                    "normalized_term": "食用香精",
                    "retrieved": True,
                    "match_quality": "high",
                    "matches": [
                        {
                            "id": "1",
                            "term": "食用香精",
                            "normalized_term": "食用香精",
                            "aliases": ["香精"],
                            "function_category": "flavoring",
                            "is_primary": True,
                            "similarity_score": 0.95,
                        },
                    ],
                },
            ],
        },
    )
    analysis = FoodHealthAnalysisOutput.model_validate(
        {
            "score": 72,
            "summary": (
                "该食品的主要风险集中在添加糖和香精使用上，虽然没有显示出极端危险成分，"
                "但长期高频摄入仍可能增加能量负担并影响日常饮食结构平衡。"
            ),
            "top_risks": ["添加糖", "香精"],
            "ingredients": [
                {
                    "name": "白砂糖",
                    "risk": "warning",
                    "description": "添加糖含量偏高，长期频繁摄入可能增加体重与代谢负担。",
                    "function_category": "sweetener",
                    "rules": ["控制添加糖摄入"],
                },
            ],
            "health_advice": [
                {
                    "group": "儿童",
                    "risk": "warning",
                    "advice": (
                        "儿童应减少此类高糖加工食品摄入频率，避免过早形成对高甜口味的依赖，"
                        "同时减少额外能量摄入对正餐和体重管理造成的干扰，并降低对零食的持续依赖。"
                    ),
                    "hint": "减少高糖零食摄入频率",
                },
                {
                    "group": "孕妇",
                    "risk": "warning",
                    "advice": (
                        "孕妇如需食用应控制分量与频次，并结合全天膳食结构统筹糖分来源，"
                        "避免零食中的额外添加糖进一步推高总能量和血糖波动风险，同时减少不必要的加餐负担。"
                    ),
                    "hint": "控制每日总糖摄入水平",
                },
                {
                    "group": "老年人",
                    "risk": "warning",
                    "advice": (
                        "老年人若存在血糖或代谢问题，应优先选择添加糖更低、成分更简单的替代食品，"
                        "并减少将此类加工零食作为日常加餐的习惯，以免持续加重代谢和膳食管理压力。"
                    ),
                    "hint": "优先选择低糖替代食品",
                },
                {
                    "group": "过敏人群",
                    "risk": "safe",
                    "advice": (
                        "过敏人群应结合自身既往过敏史查看全部配料，如对香精或特定辅料存在敏感经历，"
                        "则应先确认成分并从少量尝试开始，必要时直接避免食用。"
                    ),
                    "hint": "先核对完整过敏史记录",
                },
                {
                    "group": "一般成年人",
                    "risk": "warning",
                    "advice": (
                        "一般成年人偶尔少量食用问题不大，但不应将其作为日常高频零食或主要能量来源，"
                        "尤其不宜在已经摄入较多甜食的当天继续叠加食用。"
                    ),
                    "hint": "偶尔少量食用即可满足",
                },
            ],
        },
    )

    assert nutrition.parse_method == "table_recognition"
    assert rag_results.retrieval_results[0].matches[0].similarity_score == pytest.approx(0.95)
    assert analysis.score == 72
    assert len(analysis.health_advice) == 5


def test_analysis_data_schemas_reject_invalid_payloads() -> None:
    with pytest.raises(ValidationError):
        NutritionData.model_validate({"items": [], "parse_method": "rule"})

    with pytest.raises(ValidationError):
        RAGResults.model_validate(
            {
                "retrieval_results": [
                    {
                        "raw_term": "盐",
                        "normalized_term": "盐",
                        "retrieved": True,
                        "match_quality": "high",
                        "matches": [
                            {
                                "id": "1",
                                "term": "盐",
                                "normalized_term": "盐",
                                "aliases": [],
                                "function_category": "seasoning",
                                "is_primary": True,
                                "similarity_score": 1.2,
                            },
                        ],
                    },
                ],
            },
        )

    with pytest.raises(ValidationError):
        FoodHealthAnalysisOutput.model_validate(
            {
                "score": 80,
                "summary": (
                    "这是一段长度足够的总结文本，用于专门触发重复人群校验，"
                    "并确保主结构的其余字段都满足长度和取值约束，不会引入其他无关失败原因。"
                ),
                "top_risks": ["糖"],
                "ingredients": [
                    {
                        "name": "糖",
                        "risk": "warning",
                        "description": "长期高频摄入添加糖可能对代谢和体重控制带来持续压力。",
                        "rules": [],
                    },
                ],
                "health_advice": [
                    {
                        "group": "儿童",
                        "risk": "warning",
                        "advice": (
                            "儿童需要控制此类食品的摄入频率，避免在日常饮食中形成对高糖口味的依赖，"
                            "并减少对正餐安排和日常能量管理带来的持续干扰。"
                        ),
                        "hint": "减少日常摄入频次安排",
                    },
                ]
                * 5,
            },
        )


def test_alembic_env_uses_settings_metadata_and_offline_comparison_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_required_env(monkeypatch)

    project_root = Path(__file__).resolve().parents[1]
    env_path = project_root / "alembic" / "env.py"
    captured: dict[str, object] = {}

    class FakeAlembicConfig:
        config_file_name = None
        config_ini_section = "alembic"

        def __init__(self) -> None:
            self.options: dict[str, str] = {}

        def set_main_option(self, key: str, value: str) -> None:
            self.options[key] = value

        def get_main_option(self, key: str) -> str:
            return self.options[key]

        def get_section(self, key: str, default: dict[str, str] | None = None) -> dict[str, str]:
            return default or {}

    fake_config = FakeAlembicConfig()

    import alembic.context as alembic_context
    from app.core.config import get_settings

    @contextmanager
    def fake_begin_transaction():
        yield

    monkeypatch.setattr(alembic_context, "config", fake_config, raising=False)
    monkeypatch.setattr(alembic_context, "is_offline_mode", lambda: True)
    monkeypatch.setattr(alembic_context, "configure", lambda **kwargs: captured.setdefault("configure", kwargs))
    monkeypatch.setattr(alembic_context, "begin_transaction", fake_begin_transaction)
    monkeypatch.setattr(alembic_context, "run_migrations", lambda: captured.setdefault("ran_migrations", True))

    env_globals = runpy.run_path(str(env_path))

    assert fake_config.get_main_option("sqlalchemy.url") == get_settings().DATABASE_SYNC_URL
    assert env_globals["target_metadata"] is Base.metadata
    assert captured["ran_migrations"] is True
    assert captured["configure"]["compare_type"] is True
    assert captured["configure"]["compare_server_default"] is True
