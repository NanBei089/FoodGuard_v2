from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.services.score_calculator import calculate_health_score, format_score_breakdown
from app.workers import llm_worker, ocr_worker, rag_worker, yolo_worker
from app.workers.extractor import ingredient_extractor, nutrition_extractor

settings = get_settings()


def _pick_image() -> Path:
    images_dir = REPO_ROOT / "images"
    files = sorted(images_dir.glob("*.jpg"))
    if not files:
        raise RuntimeError(f"图片目录为空或不存在: {images_dir}")
    return files[0]


def run_full_pipeline() -> bool:
    print("=" * 60)
    print("食品标签分析全链路测试（不落库）")
    print("=" * 60)

    image_path = _pick_image()
    print(f"使用图片: {image_path.name}")
    if not image_path.exists():
        print(f"错误: 图片文件不存在 - {image_path}")
        return False

    print(f"\n1. 读取图片: {image_path}")
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    print(f"   图片大小: {len(image_bytes) / 1024:.2f} KB")

    print("\n2. YOLO目标检测...")
    try:
        bbox = yolo_worker.detect(image_bytes)
        if bbox:
            print(f"   检测到目标区域: {bbox}")
            cropped_image = yolo_worker.crop_image(image_bytes, bbox)
            print(f"   裁剪后图片大小: {len(cropped_image) / 1024:.2f} KB")
        else:
            print("   未检测到目标区域，使用原图")
            cropped_image = image_bytes
            bbox = None
    except Exception as e:
        print(f"   YOLO检测失败: {e}")
        cropped_image = image_bytes
        bbox = None

    print("\n3. OCR识别（全文 + 营养成分表）...")
    try:
        full_text_result = ocr_worker.recognize_full_text(image_bytes)
        table_result = ocr_worker.recognize_nutrition_table(cropped_image) if bbox else ocr_worker.recognize_nutrition_table(image_bytes)
        print(f"   识别文字行数: {len(full_text_result.lines)}")
        print(f"   识别文本预览 (前500字符):\n{full_text_result.raw_text[:500]}")
        print(f"   营养成分表文本: {table_result.ocr_fallback_text[:300] if table_result.ocr_fallback_text else '无'}")
    except Exception as e:
        print(f"   OCR并行识别失败: {e}")
        import traceback

        traceback.print_exc()
        full_text_result = None
        table_result = None

    if full_text_result:
        print("\n4. 营养成分解析...")
        try:
            nutrition_json = nutrition_extractor.parse(
                table_result.model_dump() if table_result else None,
                table_result.ocr_fallback_text if table_result and table_result.ocr_fallback_text else full_text_result.raw_text or None,
            )
            print(f"   解析方法: {nutrition_json.get('parse_method', 'unknown')}")
            print(f"   营养成分数量: {len(nutrition_json.get('items', []))}")
            print(f"   解析结果: {json.dumps(nutrition_json, ensure_ascii=False, indent=2)[:800]}")
        except Exception as e:
            print(f"   营养成分解析失败: {e}")
            nutrition_json = {}

        print("\n5. 配料成分提取...")
        try:
            ingredient_terms, ingredients_text = ingredient_extractor.extract(full_text_result.raw_text)
            print(f"   提取的配料数量: {len(ingredient_terms)}")
            print(f"   配料列表: {ingredient_terms}")
            print(f"   原始配料文本: {ingredients_text[:300] if ingredients_text else '无'}")
        except Exception as e:
            print(f"   配料提取失败: {e}")
            ingredient_terms = []
            ingredients_text = ""

        print("\n6. RAG检索...")
        try:
            ingredients_query = ", ".join(ingredient_terms[:10])
            rag_ingredients = rag_worker.retrieve_all_ingredients(ingredients_query, top_k=settings.RAG_TOP_K_INGREDIENTS)
            rag_standards = []
            for term in ingredient_terms[:5]:
                standards = rag_worker.query_gb2760_by_keyword(term, top_k=2)
                rag_standards.extend(standards)
            rag_output = {
                "retrieval_results": rag_ingredients,
                "standards_results": rag_standards[:10],
            }
            print(f"   RAG配料检索结果数: {len(rag_ingredients)}")
            print(f"   RAG标准检索结果数: {len(rag_standards)}")
        except Exception as e:
            print(f"   RAG检索失败（使用空结果继续）: {e}")
            rag_output = {"retrieval_results": [], "standards_results": []}

        print("\n7. LLM健康分析...")
        llm_output = None
        rule_score = None
        component_scores = None
        try:
            from app.schemas.analysis_data import IngredientItem, NutritionData

            nutrition_data = NutritionData(**nutrition_json) if nutrition_json.get("items") else None
            ingredient_items = []
            if llm_output and llm_output.get("ingredients"):
                for ing in llm_output["ingredients"]:
                    ingredient_items.append(IngredientItem(**ing))

            rag_for_llm = {
                "retrieval_results": rag_output.get("retrieval_results", []),
                "standards_results": rag_output.get("standards_results", []),
            }
            llm_output = llm_worker.analyze(
                full_text_result.raw_text,
                nutrition_json,
                rag_for_llm,
                rule_based_score=None,
            )

            if llm_output and llm_output.get("ingredients"):
                ingredient_items = []
                for ing in llm_output["ingredients"]:
                    ingredient_items.append(IngredientItem(**ing))

            rule_score, component_scores = calculate_health_score(
                nutrition_data=nutrition_data,
                ingredients=ingredient_items,
                rag_results=None,
            )

            print(f"   LLM评分: {llm_output.get('score', 'N/A')}")
            print(f"   规则计算评分: {rule_score}")
            print(f"\n{format_score_breakdown(component_scores)}")
        except Exception as e:
            print(f"   分析失败: {e}")
            import traceback

            traceback.print_exc()

    print("\n" + "=" * 60)
    print("全链路测试完成!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    run_full_pipeline()

