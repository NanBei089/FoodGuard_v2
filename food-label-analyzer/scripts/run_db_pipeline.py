from __future__ import annotations

import json
import sqlalchemy
import sys
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal as async_session_maker
from app.models.analysis_task import AnalysisTask
from app.models.enums import TaskStatus
from app.models.report import Report
from app.models.user import User
from app.schemas.analysis_data import IngredientItem, NutritionData
from app.services.score_calculator import calculate_health_score
from app.services.storage_service import StorageService
from app.workers import llm_worker, ocr_worker, rag_worker, yolo_worker
from app.workers.extractor import ingredient_extractor, nutrition_extractor


async def create_test_user(db):
    from sqlalchemy import select

    result = await db.execute(select(User).where(User.email == "test@example.com"))
    user = result.scalar_one_or_none()
    if not user:
        user = User(
            id=uuid4(),
            email="test@example.com",
            password_hash="dummy",
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


def _pick_image() -> Path:
    images_dir = REPO_ROOT / "images"
    files = sorted(images_dir.glob("*.jpg"))
    if not files:
        raise RuntimeError(f"图片目录为空或不存在: {images_dir}")
    return files[1] if len(files) > 1 else files[0]


async def main():
    print("=" * 60)
    print("食品标签分析 - 落库测试")
    print("=" * 60)

    settings = get_settings()
    print("\n配置检查:")
    print(f"  MinIO: {settings.MINIO_ENDPOINT}")
    print(f"  数据库: {settings.DATABASE_URL.split('@')[-1] if '@' in settings.DATABASE_URL else 'N/A'}")

    image_path = _pick_image()
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    print(f"\n1. 图片读取: {image_path.name} ({len(image_bytes) / 1024:.2f} KB)")

    print("\n2. YOLO目标检测...")
    cropped_image = image_bytes
    masked_image = image_bytes
    try:
        bbox = yolo_worker.detect(image_bytes)
        if bbox:
            cropped_image = yolo_worker.crop_image(image_bytes, bbox)
            masked_image = yolo_worker.mask_image(image_bytes, bbox)
            print(f"   检测成功: {bbox}")
        else:
            print("   未检测到，使用原图")
    except Exception as e:
        print(f"   检测失败，使用原图: {e}")

    print("\n3. OCR并行识别...")
    full_text_result = ocr_worker.recognize_full_text(image_bytes)
    table_result = ocr_worker.recognize_nutrition_table(cropped_image) if bbox else ocr_worker.recognize_nutrition_table(image_bytes)
    print(f"   识别文字: {len(full_text_result.lines)} 行")

    print("\n4. 营养成分解析...")
    try:
        nutrition_json = nutrition_extractor.parse(
            table_result.model_dump(),
            table_result.ocr_fallback_text,
        )
        print(f"   解析方法: {nutrition_json.get('parse_method')}")
        print(f"   营养成分: {len(nutrition_json.get('items', []))} 项")
    except Exception as e:
        print(f"   解析失败: {e}")
        nutrition_json = {"items": [], "parse_method": "failed"}

    print("\n5. 配料提取...")
    try:
        ingredient_terms, ingredients_text = ingredient_extractor.extract(full_text_result.raw_text)
        print(f"   配料数量: {len(ingredient_terms)}")
    except Exception as e:
        print(f"   提取失败: {e}")
        ingredient_terms, ingredients_text = [], ""

    print("\n6. RAG检索...")
    try:
        rag_ingredients = rag_worker.retrieve_all_ingredients(", ".join(ingredient_terms[:10]), top_k=5)
        rag_standards = []
        for term in ingredient_terms[:5]:
            rag_standards.extend(rag_worker.query_gb2760_by_keyword(term, top_k=2))
        rag_output = {"retrieval_results": rag_ingredients, "standards_results": rag_standards[:10]}
        print(f"   RAG结果: {len(rag_ingredients)} 配料 + {len(rag_standards)} 标准")
    except Exception as e:
        print(f"   RAG失败: {e}")
        rag_output = {"retrieval_results": [], "standards_results": []}

    print("\n7. LLM健康分析...")
    try:
        llm_output = llm_worker.analyze(
            full_text_result.raw_text,
            nutrition_json,
            rag_output,
        )
        print(f"   LLM评分: {llm_output.get('score')}")
    except Exception as e:
        print(f"   LLM失败: {e}")
        llm_output = {"score": 0, "summary": "", "top_risks": [], "ingredients": [], "health_advice": []}

    print("\n8. 规则评分...")
    try:
        nutrition_data = NutritionData(**nutrition_json) if nutrition_json.get("items") else None
        ingredient_items = [IngredientItem(**ing) for ing in llm_output.get("ingredients", []) if ing.get("name")]
        rule_score, _ = calculate_health_score(nutrition_data, ingredient_items)
        print(f"   规则评分: {rule_score}")
    except Exception as e:
        print(f"   评分失败: {e}")
        rule_score = 0

    print("\n9. MinIO上传...")
    storage = StorageService()
    minio_image_key = None
    artifact_urls = {}
    try:
        await storage.ensure_bucket()
        original_key = f"original/{uuid4()}.jpg"
        await storage.upload_artifact(image_bytes, original_key, "image/jpeg")
        artifact_urls["original"] = original_key

        if cropped_image != image_bytes:
            nutrition_crop_key = f"crops/{uuid4()}.jpg"
            await storage.upload_artifact(cropped_image, nutrition_crop_key, "image/jpeg")
            artifact_urls["nutrition_crop"] = nutrition_crop_key

        if masked_image != image_bytes:
            masked_key = f"masked/{uuid4()}.jpg"
            await storage.upload_artifact(masked_image, masked_key, "image/jpeg")
            artifact_urls["masked"] = masked_key

        minio_image_key = original_key
        print(f"   原始图上传: {original_key}")
        if "nutrition_crop" in artifact_urls:
            print(f"   营养成分表裁剪图: {artifact_urls['nutrition_crop']}")
        if "masked" in artifact_urls:
            print(f"   遮挡图上传: {artifact_urls['masked']}")
    except Exception as e:
        print(f"   上传失败: {e}")

    print("\n10. 数据库落库...")
    async with async_session_maker() as db:
        try:
            user = await create_test_user(db)

            task = AnalysisTask(
                id=uuid4(),
                user_id=user.id,
                image_url=f"minio://test-bucket/{minio_image_key}",
                image_key=minio_image_key,
            )
            db.add(task)
            await db.flush()

            await db.execute(
                sqlalchemy.update(AnalysisTask).where(AnalysisTask.id == task.id).values(status=TaskStatus.COMPLETED.value)
            )

            report = Report(
                task_id=task.id,
                user_id=user.id,
                ingredients_text=ingredients_text[:2000] if ingredients_text else None,
                nutrition_json=nutrition_json,
                rag_results_json=rag_output,
                llm_output_json=llm_output,
                score=rule_score,
                artifact_urls=artifact_urls if artifact_urls else None,
            )
            db.add(report)
            await db.commit()
            await db.refresh(report)

            print(f"   任务创建: {task.id}")
            print(f"   报告创建: {report.id}")
            print(f"   状态: {task.status}")
            print(f"   评分: {report.score}")
        except Exception as e:
            print(f"   数据库落库失败: {e}")
            import traceback

            traceback.print_exc()

    print("\n" + "=" * 60)
    print("落库测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())

