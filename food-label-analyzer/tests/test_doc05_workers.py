from __future__ import annotations

import importlib
import io
import json
import uuid
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from app.core.errors import EmbeddingServiceError, LLMServiceError, OCRServiceError
from app.schemas.analysis_data import SUPPORTED_HEALTH_ADVICE_GROUPS
from tests.conftest import load_required_env


def _image_bytes(size: tuple[int, int] = (640, 640)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color=(255, 255, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


def _health_advice_payload() -> list[dict[str, str]]:
    def bounded_text(base: str, minimum: int, maximum: int) -> str:
        text = base
        while len(text) < minimum:
            text += base
        return text[:maximum]

    return [
        {
            "group": group,
            "risk": "warning",
            "advice": bounded_text(
                f"{group}建议适量食用并控制频率，关注钠糖摄入和个人敏感成分反应，搭配清淡饮食与充足饮水。",
                60,
                80,
            ),
            "hint": bounded_text("控制频率并留意反应", 10, 22),
        }
        for group in sorted(SUPPORTED_HEALTH_ADVICE_GROUPS)
    ]


def _valid_llm_payload() -> dict[str, object]:
    def bounded_text(base: str, minimum: int, maximum: int) -> str:
        text = base
        while len(text) < minimum:
            text += base
        return text[:maximum]

    return {
        "score": 86,
        "summary": bounded_text(
            "这是一段用于测试的食品健康分析总结文本，强调整体配料结构、营养风险和食用建议。",
            60,
            100,
        ),
        "top_risks": ["高钠", "添加糖"],
        "ingredients": [
            {
                "name": "食盐",
                "risk": "warning",
                "description": bounded_text(
                    "食盐摄入过多可能增加钠负担，需控制整体食用频率和单次摄入量。",
                    22,
                    60,
                ),
                "function_category": "调味剂",
                "rules": ["GB2760-2024"],
            }
        ],
        "health_advice": _health_advice_payload(),
    }


class _FakeInput:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeResponse:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError("boom", request=None, response=None)


class _SequenceClient:
    def __init__(self, responses: list[object]) -> None:
        self.responses = list(responses)
        self.calls = 0

    def post(self, *args, **kwargs):
        response = self.responses[self.calls]
        self.calls += 1
        if isinstance(response, Exception):
            raise response
        return response


def test_yolo_detect_returns_bbox_from_mocked_session(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)
    yolo_module = importlib.reload(importlib.import_module("app.workers.yolo_worker"))
    class _FakeTensor:
        def __init__(self, value):
            self._value = value

        def cpu(self):
            return self

        def tolist(self):
            return self._value

    class _FakeBoxes:
        def __init__(self):
            self.xyxy = _FakeTensor([[10.0, 20.0, 110.0, 220.0]])
            self.conf = _FakeTensor([0.9])
            self.cls = _FakeTensor([0.0])

        def __len__(self):
            return 1

    class _FakeResult:
        orig_shape = (300, 400)
        boxes = _FakeBoxes()

    class FakeModel:
        def predict(self, *args, **kwargs):
            return [_FakeResult()]

    monkeypatch.setattr(yolo_module, "_get_model", lambda: FakeModel())
    bbox = yolo_module.detect(_image_bytes())
    assert bbox == {"x1": 10, "y1": 20, "x2": 110, "y2": 220, "confidence": 0.9}


def test_yolo_crop_image_clamps_padding(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)
    yolo_module = importlib.reload(importlib.import_module("app.workers.yolo_worker"))
    cropped = yolo_module.crop_image(
        _image_bytes((30, 20)),
        {"x1": 0, "y1": 0, "x2": 10, "y2": 10},
        padding=20,
    )
    assert cropped[:2] == b"\xff\xd8"


def test_yolo_detect_returns_none_on_session_error(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)
    yolo_module = importlib.reload(importlib.import_module("app.workers.yolo_worker"))
    class FakeModel:
        def predict(self, *args, **kwargs):
            raise RuntimeError("no model")

    monkeypatch.setattr(yolo_module, "_get_model", lambda: FakeModel())
    assert yolo_module.detect(_image_bytes()) is None


def test_yolo_warmup_calls_predict(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)
    yolo_module = importlib.reload(importlib.import_module("app.workers.yolo_worker"))

    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    class FakeModel:
        def predict(self, *args, **kwargs):
            calls.append((args, kwargs))
            return []

    monkeypatch.setattr(yolo_module, "_get_model", lambda: FakeModel())
    yolo_module.warmup()
    assert calls


def test_ocr_post_image_retries_server_error(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)
    ocr_module = importlib.reload(importlib.import_module("app.workers.ocr_worker"))
    monkeypatch.setattr(ocr_module, "_get_ocr_engine", lambda: SimpleNamespace(ocr=lambda _: {"lines": [{"text": "ok"}]}))
    result = ocr_module.recognize_full_text(_image_bytes((32, 32)))
    assert result.raw_text == "ok"


def test_ocr_post_image_raises_on_client_error(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)
    ocr_module = importlib.reload(importlib.import_module("app.workers.ocr_worker"))
    monkeypatch.setattr(
        ocr_module,
        "_get_ocr_engine",
        lambda: SimpleNamespace(ocr=lambda _: (_ for _ in ()).throw(RuntimeError("bad"))),
    )
    with pytest.raises(OCRServiceError):
        ocr_module.recognize_full_text(_image_bytes((32, 32)))


def test_ocr_recognize_full_text_normalizes_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)
    ocr_module = importlib.reload(importlib.import_module("app.workers.ocr_worker"))
    monkeypatch.setattr(
        ocr_module,
        "_get_ocr_engine",
        lambda: SimpleNamespace(ocr=lambda _: {"lines": [{"text": "配料：盐"}]}),
    )
    result = ocr_module.recognize_full_text(_image_bytes((32, 32)))
    assert result.raw_text == "配料：盐"


def test_ocr_recognize_nutrition_table_normalizes_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)
    ocr_module = importlib.reload(importlib.import_module("app.workers.ocr_worker"))
    table_html = (
        "<table><tr><td>项目</td><td>每100g</td><td>NRV%</td></tr>"
        "<tr><td>能量</td><td>100kJ</td><td>1%</td></tr></table>"
    )
    monkeypatch.setattr(
        ocr_module,
        "_get_ocr_engine",
        lambda: SimpleNamespace(
            ocr=lambda _: {
                "results": [
                    {
                        "layoutParsingResults": [
                            {
                                "prunedResult": {
                                    "parsing_res_list": [
                                        {"block_label": "table", "block_content": table_html}
                                    ]
                                }
                            }
                        ]
                    }
                ]
            }
        ),
    )

    result = ocr_module.recognize_nutrition_table(_image_bytes((32, 32)))
    assert result.table_json is not None


def test_ocr_warmup_probes_both_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)
    ocr_module = importlib.reload(importlib.import_module("app.workers.ocr_worker"))
    ocr_module.warmup()


def test_nutrition_parse_prefers_table_result(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)
    nutrition_module = importlib.reload(importlib.import_module("app.workers.extractor.nutrition_extractor"))

    result = nutrition_module.parse(
        {"table_json": {"rows": [["能量", "100kJ", "1%"], ["蛋白质", "2g", "3%"]]}},
        None,
    )

    assert result["parse_method"] == "table_recognition"
    assert result["items"][0]["name"] == "能量"


def test_nutrition_parse_falls_back_to_ocr_text(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)
    nutrition_module = importlib.reload(importlib.import_module("app.workers.extractor.nutrition_extractor"))

    result = nutrition_module.parse(None, "每100g\n能量 120kJ 2%\n蛋白质 3g 5%")

    assert result["parse_method"] == "ocr_text"
    assert len(result["items"]) == 2


def test_nutrition_parse_uses_llm_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)
    nutrition_module = importlib.reload(importlib.import_module("app.workers.extractor.nutrition_extractor"))
    monkeypatch.setattr(nutrition_module, "_parse_from_ocr_text", lambda text: None)
    monkeypatch.setattr(
        nutrition_module,
        "_llm_fallback",
        lambda text: {"items": [], "serving_size": None, "parse_method": "llm_fallback"},
    )

    result = nutrition_module.parse(None, "无法规则解析的内容")

    assert result["parse_method"] == "llm_fallback"


def test_ingredient_extract_rule_and_expand(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)
    ingredient_module = importlib.reload(importlib.import_module("app.workers.extractor.ingredient_extractor"))

    ingredients, raw_text = ingredient_module.extract("配料：白砂糖、复合调味料（食盐、味精）、水\n净含量 200g")

    assert raw_text.startswith("白砂糖")
    assert ingredients == ["白砂糖", "复合调味料", "食盐", "味精", "水"]


def test_ingredient_extract_llm_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)
    ingredient_module = importlib.reload(importlib.import_module("app.workers.extractor.ingredient_extractor"))
    monkeypatch.setattr(ingredient_module, "_locate_ingredients_text", lambda text: ("", False))
    monkeypatch.setattr(ingredient_module, "_llm_extract", lambda text: ["牛肉", "食盐"])

    ingredients, raw_text = ingredient_module.extract("没有显式配料关键词")

    assert ingredients == ["牛肉", "食盐"]
    assert raw_text == "(LLM提取)"


def test_rag_embed_uses_ollama_api(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)
    rag_module = importlib.reload(importlib.import_module("app.workers.rag_worker"))

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"embeddings": [[0.1, 0.2, 0.3]]}

    class FakeClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, object]]] = []

        def post(self, url: str, json: dict[str, object]):
            self.calls.append((url, json))
            return FakeResponse()

    fake_client = FakeClient()
    monkeypatch.setattr(rag_module, "_get_http_client", lambda: fake_client)

    vector = rag_module._embed("配料：食盐")

    assert vector == [0.1, 0.2, 0.3]
    assert fake_client.calls[0][0].endswith("/api/embed")
    assert fake_client.calls[0][1]["model"]
    assert fake_client.calls[0][1]["input"] == "配料:食盐"


def test_rag_warmup_raises_when_any_collection_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)
    rag_module = importlib.reload(importlib.import_module("app.workers.rag_worker"))
    monkeypatch.setattr(
        rag_module,
        "_get_ingredients_collection",
        lambda: (_ for _ in ()).throw(RuntimeError("missing ingredients")),
    )
    monkeypatch.setattr(rag_module, "_get_standards_collection", lambda: SimpleNamespace())

    with pytest.raises(RuntimeError):
        rag_module.warmup()


def test_rag_warmup_succeeds_when_collections_available(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)
    rag_module = importlib.reload(importlib.import_module("app.workers.rag_worker"))
    calls: list[str] = []
    monkeypatch.setattr(rag_module, "_get_ingredients_collection", lambda: SimpleNamespace())
    monkeypatch.setattr(rag_module, "_get_standards_collection", lambda: SimpleNamespace())
    monkeypatch.setattr(rag_module, "_embed", lambda text: calls.append(text) or [0.1, 0.2])
    rag_module.warmup()
    assert calls == ["食品配料"]


def test_rag_retrieve_all_returns_schema_compatible_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)
    rag_module = importlib.reload(importlib.import_module("app.workers.rag_worker"))
    monkeypatch.setattr(
        rag_module,
        "retrieve_all_ingredients",
        lambda query_text, top_k=5: [
            {
                "id": "ing-1",
                "document": "食用香精",
                "metadata": {
                    "term": "食用香精",
                    "normalized_term": "食用香精",
                    "aliases": ["香精"],
                    "category": "flavoring",
                },
                "distance": 0.08,
            }
        ],
    )
    monkeypatch.setattr(
        rag_module,
        "query_gb2760_by_keyword",
        lambda keyword, top_k=3: [
            {
                "id": "std-1",
                "document": "允许使用",
                "metadata": {
                    "term": keyword,
                    "normalized_term": keyword,
                    "aliases": [],
                    "function_category": "standard",
                    "is_primary": False,
                },
                "distance": 0.22,
            }
        ],
    )

    result = rag_module.retrieve_all(["食用香精"], "配料：食用香精")

    assert result["source_file"] == "chromadb"
    assert result["ingredients_text"] == "配料：食用香精"
    assert result["items_total"] == 1
    retrieval_item = result["retrieval_results"][0]
    assert retrieval_item["raw_term"] == "食用香精"
    assert retrieval_item["normalized_term"] == "食用香精"
    assert retrieval_item["retrieved"] is True
    assert retrieval_item["match_quality"] == "high"
    assert len(retrieval_item["matches"]) == 2
    assert retrieval_item["matches"][0]["function_category"] == "flavoring"
    assert retrieval_item["matches"][0]["similarity_score"] == pytest.approx(0.92)


def test_llm_analyze_returns_validated_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)
    llm_module = importlib.reload(importlib.import_module("app.workers.llm_worker"))
    monkeypatch.setattr(llm_module, "validate_configuration", lambda: None)
    payload = _valid_llm_payload()
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload, ensure_ascii=False)))]
    )
    monkeypatch.setattr(
        llm_module,
        "_get_client",
        lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: response))),
    )

    result = llm_module.analyze("配料：盐", {"items": [], "parse_method": "empty"}, {"retrieval_results": []})

    assert result["score"] == 86
    assert len(result["health_advice"]) == 5


def test_llm_analyze_repairs_invalid_output(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)
    llm_module = importlib.reload(importlib.import_module("app.workers.llm_worker"))
    monkeypatch.setattr(llm_module, "validate_configuration", lambda: None)
    responses = iter(
        [
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"score": 1}'))]),
            SimpleNamespace(
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content=json.dumps(_valid_llm_payload(), ensure_ascii=False)))
                ]
            ),
        ]
    )
    monkeypatch.setattr(
        llm_module,
        "_get_client",
        lambda: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: next(responses))),
        ),
    )

    result = llm_module.analyze("配料：盐", {"items": [], "parse_method": "empty"}, {"retrieval_results": []})

    assert result["score"] == 86


def test_llm_analyze_raises_when_repair_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch, DEEPSEEK_MAX_RETRIES="1")
    llm_module = importlib.reload(importlib.import_module("app.workers.llm_worker"))
    monkeypatch.setattr(llm_module, "validate_configuration", lambda: None)
    bad_response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"score": 1}'))])
    monkeypatch.setattr(
        llm_module,
        "_get_client",
        lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: bad_response))),
    )

    with pytest.raises(LLMServiceError):
        llm_module.analyze("配料：盐", {"items": [], "parse_method": "empty"}, {"retrieval_results": []})


def test_celery_worker_init_runs_warmups_and_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)
    celery_module = importlib.reload(importlib.import_module("app.tasks.celery_app"))
    calls: list[str] = []

    monkeypatch.setattr(celery_module, "setup_logging", lambda level, fmt: calls.append("logging"))
    monkeypatch.setattr(celery_module.yolo_worker, "warmup", lambda: calls.append("yolo"))
    monkeypatch.setattr(celery_module.ocr_worker, "warmup", lambda: calls.append("ocr"))
    monkeypatch.setattr(celery_module.rag_worker, "warmup", lambda: calls.append("rag"))
    monkeypatch.setattr(celery_module.llm_worker, "validate_configuration", lambda: calls.append("llm"))

    celery_module._initialize_worker_resources()

    assert calls == ["logging", "yolo", "ocr", "rag", "llm"]


def test_celery_worker_init_does_not_raise_on_nonfatal_warmup(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)
    celery_module = importlib.reload(importlib.import_module("app.tasks.celery_app"))
    monkeypatch.setattr(celery_module, "setup_logging", lambda level, fmt: None)
    monkeypatch.setattr(celery_module.yolo_worker, "warmup", lambda: None)
    monkeypatch.setattr(celery_module.ocr_worker, "warmup", lambda: (_ for _ in ()).throw(OCRServiceError("down")))
    monkeypatch.setattr(celery_module.rag_worker, "warmup", lambda: None)
    monkeypatch.setattr(celery_module.llm_worker, "validate_configuration", lambda: None)

    celery_module._initialize_worker_resources()
