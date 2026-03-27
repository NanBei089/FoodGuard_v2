from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


class TestOCRTopicRules:
    @pytest.fixture
    def demo_result_path(self) -> Path:
        return Path(__file__).parent.parent.parent / "demo" / "upload_results"

    @pytest.fixture
    def first_ocr_result(self, demo_result_path: Path) -> Path | None:
        if not demo_result_path.exists():
            return None
        for result_dir in sorted(demo_result_path.iterdir()):
            if result_dir.is_dir():
                ocr_json_path = result_dir / "other.ocr.json"
                if ocr_json_path.exists():
                    return ocr_json_path
        return None

    def test_ocr_topic_rules_with_demo_data(
        self, first_ocr_result: Path | None
    ) -> None:
        from app.workers.extractor.ingredients_only import build_ingredients_output
        from app.workers.extractor.topic_cleaner import clean_ocr_text
        from app.workers.extractor.topic_splitter import (
            extract_ingredient_topic,
            extract_other_topics,
        )

        if first_ocr_result is None:
            pytest.skip("No demo OCR results found for testing")

        print(f"\nTesting with demo result: {first_ocr_result}")

        with open(first_ocr_result, "r", encoding="utf-8") as f:
            ocr_data = json.load(f)

        raw_text = ocr_data.get("raw_text", "")
        lines = ocr_data.get("lines", [])

        assert len(raw_text) > 0, "Raw text should not be empty"

        cleaned = clean_ocr_text(raw_text=raw_text, lines=lines)
        assert len(cleaned["clean_text"]) > 0, "Clean text should not be empty"
        assert len(cleaned["clean_lines"]) > 0, "Should have clean lines"

        ingredient_topic = extract_ingredient_topic(
            clean_text=cleaned["clean_text"],
            flat_text=cleaned["flat_text"],
            clean_lines=cleaned.get("clean_lines"),
        )
        assert "found" in ingredient_topic
        assert "text" in ingredient_topic

        ingredients_output = build_ingredients_output(
            ingredient_topic=ingredient_topic,
            roi_id="test_roi",
            input_json=str(first_ocr_result),
        )
        assert "found" in ingredients_output
        assert "items" in ingredients_output

        other_topics = extract_other_topics(
            clean_text=cleaned["clean_text"],
            clean_lines=cleaned.get("clean_lines"),
        )
        assert isinstance(other_topics, dict)

    def test_clean_ocr_text_with_empty_input(self) -> None:
        from app.workers.extractor.topic_cleaner import clean_ocr_text

        with pytest.raises(ValueError):
            clean_ocr_text("", None)

    def test_extract_ingredient_topic_with_empty_input(self) -> None:
        from app.workers.extractor.topic_splitter import extract_ingredient_topic

        with pytest.raises(ValueError):
            extract_ingredient_topic("", "")

    def test_extract_other_topics_returns_all_topics(self) -> None:
        from app.workers.extractor.rule_config import OTHER_TOPIC_ORDER
        from app.workers.extractor.topic_splitter import extract_other_topics

        result = extract_other_topics(
            clean_text="一些测试文本配料表：面粉、水、盐。保质期：12个月。",
            clean_lines=["一些测试文本", "配料表：面粉、水、盐。", "保质期：12个月。"],
        )

        assert isinstance(result, dict)
        for topic in OTHER_TOPIC_ORDER:
            assert topic in result


class TestRuleConfig:
    def test_rule_config_imports(self) -> None:
        from app.workers.extractor.rule_config import (
            INGREDIENT_END_RE,
            INGREDIENT_LABEL_RE,
            MANUFACTURER_LINE_RE,
            OTHER_TOPIC_PATTERNS,
        )

        assert INGREDIENT_LABEL_RE is not None
        assert INGREDIENT_END_RE is not None
        assert isinstance(OTHER_TOPIC_PATTERNS, dict)
        assert MANUFACTURER_LINE_RE is not None
