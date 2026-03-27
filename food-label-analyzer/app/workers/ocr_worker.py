from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

import requests
import structlog
from PIL import Image

from app.core.config import get_settings
from app.core.errors import OCRServiceError

logger = structlog.get_logger(__name__)

_ENGINE_CACHE: dict[str, "PaddleOCRAPIClient"] = {}
_engine_lock = threading.Lock()


@dataclass(frozen=True)
class OCRConfig:
    job_url: str
    token: str
    model: str = "PaddleOCR-VL-1.5"
    lang: str = "ch"
    use_angle_cls: bool = True
    det: bool = True
    rec: bool = True
    det_db_box_thresh: float = 0.5
    det_db_unclip_ratio: float = 1.8
    rec_char_type: str = "ch"
    device: str = "cpu"

    use_doc_orientation_classify: bool = True
    use_doc_unwarping: bool = True
    use_textline_orientation: bool = True
    use_seal_recognition: bool = False

    use_table_recognition: bool = True
    use_e2e_wired_table_rec_model: bool = False
    use_e2e_wireless_table_rec_model: bool = True

    use_formula_recognition: bool = False
    use_chart_recognition: bool = False

    text_det_limit_side_len: int = 960
    text_det_limit_type: str = "max"
    text_det_thresh: float = 0.3

    poll_interval_s: float = 5.0
    poll_timeout_s: float = 300.0
    request_timeout_s: float = 60.0


class OCRTextResult:
    def __init__(
        self,
        raw_text: str = "",
        lines: list[dict[str, Any]] | None = None,
        blocks: list[dict[str, Any]] | None = None,
        source: Literal["ocr_runtime"] = "ocr_runtime",
        artifact_json_url: str | None = None,
    ) -> None:
        self.raw_text = raw_text
        self.lines = lines or []
        self.blocks = blocks or []
        self.source = source
        self.artifact_json_url = artifact_json_url

    def model_dump(self) -> dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "lines": self.lines,
            "blocks": self.blocks,
            "source": self.source,
            "artifact_json_url": self.artifact_json_url,
        }


class TableRecognitionResult:
    def __init__(
        self,
        table_json: dict[str, Any] | None = None,
        table_html_url: str | None = None,
        table_xlsx_url: str | None = None,
        ocr_fallback_text: str | None = None,
        source: Literal["ocr_runtime"] = "ocr_runtime",
    ) -> None:
        self.table_json = table_json
        self.table_html_url = table_html_url
        self.table_xlsx_url = table_xlsx_url
        self.ocr_fallback_text = ocr_fallback_text
        self.source = source

    def model_dump(self) -> dict[str, Any]:
        return {
            "table_json": self.table_json,
            "table_html_url": self.table_html_url,
            "table_xlsx_url": self.table_xlsx_url,
            "ocr_fallback_text": self.ocr_fallback_text,
            "source": self.source,
        }


class PaddleOCRAPIClient:
    def __init__(self, config: OCRConfig) -> None:
        self.config = config
        if not config.job_url.strip():
            raise RuntimeError("PaddleOCR 在线 JOB_URL 未配置。")
        if not config.token.strip():
            raise RuntimeError("PaddleOCR 在线 TOKEN 未配置。")
        if not config.model.strip():
            raise RuntimeError("PaddleOCR 在线 MODEL 未配置。")

    def describe(self) -> dict[str, Any]:
        return {
            "lang": self.config.lang,
            "use_angle_cls": self.config.use_angle_cls,
            "model": self.config.model,
            "mode": "online_api",
            "device": self.config.device,
        }

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"bearer {self.config.token}"}

    def _build_optional_payload(self) -> dict[str, Any]:
        return {
            "useDocOrientationClassify": bool(self.config.use_doc_orientation_classify),
            "useDocUnwarping": bool(self.config.use_doc_unwarping),
            "useTextlineOrientation": bool(self.config.use_textline_orientation),
            "useSealRecognition": bool(self.config.use_seal_recognition),
            "useTableRecognition": bool(self.config.use_table_recognition),
            "useE2eWiredTableRecModel": bool(self.config.use_e2e_wired_table_rec_model),
            "useE2eWirelessTableRecModel": bool(
                self.config.use_e2e_wireless_table_rec_model
            ),
            "useFormulaRecognition": bool(self.config.use_formula_recognition),
            "useChartRecognition": bool(self.config.use_chart_recognition),
            "textDetBoxThresh": float(self.config.det_db_box_thresh),
            "textDetUnclipRatio": float(self.config.det_db_unclip_ratio),
            "textDetLimitSideLen": int(self.config.text_det_limit_side_len),
            "textDetLimitType": str(self.config.text_det_limit_type),
            "textDetThresh": float(self.config.text_det_thresh),
        }

    def _submit_job(self, image_bytes: bytes, filename: str = "image.jpg") -> str:
        data = {
            "model": self.config.model,
            "optionalPayload": json.dumps(
                self._build_optional_payload(), ensure_ascii=False
            ),
        }
        files = {"file": (filename, image_bytes, "application/octet-stream")}
        response = requests.post(
            self.config.job_url,
            headers=self._headers(),
            data=data,
            files=files,
            timeout=self.config.request_timeout_s,
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"提交 OCR 任务失败，HTTP {response.status_code}: {response.text}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("提交 OCR 任务后返回了无法解析的 JSON。") from exc

        try:
            return str(payload["data"]["jobId"])
        except Exception as exc:
            raise RuntimeError(f"提交 OCR 任务成功但响应缺少 jobId: {payload}") from exc

    def _poll_job(self, job_id: str) -> dict[str, Any]:
        job_status_url = f"{self.config.job_url}/{job_id}"
        deadline = time.monotonic() + self.config.poll_timeout_s

        while time.monotonic() < deadline:
            response = requests.get(
                job_status_url,
                headers=self._headers(),
                timeout=self.config.request_timeout_s,
            )
            if response.status_code != 200:
                raise RuntimeError(
                    f"轮询 OCR 任务失败，HTTP {response.status_code}: {response.text}"
                )

            try:
                payload = response.json()
            except ValueError as exc:
                raise RuntimeError("轮询 OCR 任务时返回了无法解析的 JSON。") from exc

            data = payload.get("data") or {}
            state = data.get("state")
            if state == "done":
                return data
            if state == "failed":
                raise RuntimeError(
                    f"OCR 任务失败: {data.get('errorMsg', 'unknown error')}"
                )
            if state not in {"pending", "running"}:
                raise RuntimeError(f"OCR 任务状态异常: {payload}")

            time.sleep(self.config.poll_interval_s)

        raise TimeoutError(
            f"OCR 任务超时，超过 {self.config.poll_timeout_s} 秒仍未完成。job_id={job_id}"
        )

    def _download_jsonl_results(self, json_url: str) -> list[Any]:
        response = requests.get(json_url, timeout=self.config.request_timeout_s)
        response.raise_for_status()

        response_text = response.content.decode("utf-8", errors="replace")
        results: list[Any] = []
        for raw_line in response_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if isinstance(item, dict) and "result" in item:
                results.append(item["result"])
            else:
                results.append(item)
        return results

    def ocr(self, image_bytes: bytes, filename: str = "image.jpg") -> dict[str, Any]:
        job_id = self._submit_job(image_bytes, filename)
        job_data = self._poll_job(job_id)
        result_url = job_data.get("resultUrl") or {}
        json_url = result_url.get("jsonUrl") or result_url.get("jsonlUrl")
        if not json_url:
            raise RuntimeError(f"OCR 任务完成但缺少 jsonUrl: {job_data}")

        results = self._download_jsonl_results(str(json_url))
        return {
            "job_id": job_id,
            "json_url": str(json_url),
            "results": results,
        }


PaddleOCR = PaddleOCRAPIClient


def _ensure_file(path: str | Path) -> Path:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"图片文件不存在: {file_path}")
    if not file_path.is_file():
        raise FileNotFoundError(f"图片路径不是有效文件: {file_path}")
    return file_path


def _prepare_image_for_remote_ocr(
    image_bytes: bytes,
    *,
    max_side: int = 2200,
    jpeg_quality: int = 86,
) -> bytes:
    try:
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return image_bytes

    original_size = image.size
    processed = image.copy()
    processed.thumbnail((max_side, max_side))

    output = BytesIO()
    try:
        processed.save(output, format="JPEG", quality=jpeg_quality, optimize=True)
    except Exception:
        return image_bytes

    optimized = output.getvalue()
    if not optimized:
        return image_bytes

    logger.info(
        "ocr_image_prepared",
        original_bytes=len(image_bytes),
        prepared_bytes=len(optimized),
        original_size=original_size,
        prepared_size=processed.size,
    )
    return optimized if len(optimized) < len(image_bytes) else image_bytes


def _coerce_number(value: Any) -> int | float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number.is_integer():
        return int(number)
    return round(number, 4)


def _coerce_score(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _repair_text(text: str) -> str:
    for source_encoding in ("gbk", "gb18030"):
        try:
            repaired = text.encode(source_encoding).decode("utf-8")
        except UnicodeError:
            continue
        if repaired:
            return repaired
    return text


def _normalize_point(point: Any) -> list[int | float] | None:
    if isinstance(point, dict):
        if "x" in point and "y" in point:
            return [_coerce_number(point["x"]), _coerce_number(point["y"])]
        return None
    if isinstance(point, (list, tuple)) and len(point) >= 2:
        return [_coerce_number(point[0]), _coerce_number(point[1])]
    return None


def _normalize_bbox(raw_bbox: Any) -> list[list[int | float]]:
    if isinstance(raw_bbox, (list, tuple)) and len(raw_bbox) == 8:
        raw_bbox = [raw_bbox[0:2], raw_bbox[2:4], raw_bbox[4:6], raw_bbox[6:8]]

    if isinstance(raw_bbox, (list, tuple)):
        points: list[list[int | float]] = []
        for point in raw_bbox:
            normalized = _normalize_point(point)
            if normalized is not None:
                points.append(normalized)
        if len(points) >= 4:
            return points[:4]
        return points
    return []


def _is_local_line(item: Any) -> bool:
    return (
        isinstance(item, (list, tuple))
        and len(item) == 2
        and isinstance(item[1], (list, tuple))
        and len(item[1]) >= 2
    )


def _build_line(text: Any, score: Any, bbox: Any) -> dict[str, Any]:
    normalized_text = "" if text is None else _repair_text(str(text))
    return {
        "text": normalized_text,
        "score": _coerce_score(score),
        "bbox": _normalize_bbox(bbox),
    }


def _extract_from_layout_results(layout_results: list[Any]) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for item in layout_results:
        if not isinstance(item, dict):
            continue
        markdown = item.get("markdown")
        text_block = ""
        if isinstance(markdown, dict):
            text_block = str(markdown.get("text") or "")
        elif isinstance(item.get("text"), str):
            text_block = item["text"]
        bbox = (
            item.get("bbox")
            or item.get("box")
            or item.get("region")
            or item.get("poly")
            or []
        )
        for text_line in text_block.splitlines():
            stripped = text_line.strip()
            if stripped:
                lines.append(_build_line(text=stripped, score=1.0, bbox=bbox))
    return lines


def extract_text_lines(ocr_result: Any) -> list[dict[str, Any]]:
    if ocr_result is None:
        return []

    if isinstance(ocr_result, dict):
        if "results" in ocr_result:
            return extract_text_lines(ocr_result["results"])

        if "result" in ocr_result:
            return extract_text_lines(ocr_result["result"])

        if "ocrResults" in ocr_result and isinstance(ocr_result["ocrResults"], list):
            lines: list[dict[str, Any]] = []
            for item in ocr_result["ocrResults"]:
                if isinstance(item, dict) and "prunedResult" in item:
                    lines.extend(extract_text_lines(item["prunedResult"]))
                else:
                    lines.extend(extract_text_lines(item))
            return lines

        if "prunedResult" in ocr_result:
            return extract_text_lines(ocr_result["prunedResult"])

        if "rec_texts" in ocr_result and isinstance(ocr_result["rec_texts"], list):
            texts = ocr_result.get("rec_texts") or []
            scores = ocr_result.get("rec_scores") or []
            boxes = (
                ocr_result.get("dt_polys")
                or ocr_result.get("rec_polys")
                or ocr_result.get("textline_polys")
                or []
            )
            total = max(len(texts), len(scores), len(boxes))
            lines = []
            for index in range(total):
                text = texts[index] if index < len(texts) else ""
                score = scores[index] if index < len(scores) else 0.0
                bbox = boxes[index] if index < len(boxes) else []
                line = _build_line(text=text, score=score, bbox=bbox)
                if line["text"] or line["bbox"]:
                    lines.append(line)
            return lines

        if "layoutParsingResults" in ocr_result and isinstance(
            ocr_result["layoutParsingResults"], list
        ):
            return _extract_from_layout_results(ocr_result["layoutParsingResults"])

        if "lines" in ocr_result and isinstance(ocr_result["lines"], list):
            return [
                _build_line(
                    text=line.get("text"),
                    score=line.get("score"),
                    bbox=line.get("bbox"),
                )
                for line in ocr_result["lines"]
                if isinstance(line, dict)
            ]

    if isinstance(ocr_result, list):
        if not ocr_result:
            return []

        if all(_is_local_line(item) for item in ocr_result):
            return [
                _build_line(text=item[1][0], score=item[1][1], bbox=item[0])
                for item in ocr_result
            ]

        lines: list[dict[str, Any]] = []
        for item in ocr_result:
            lines.extend(extract_text_lines(item))
        return lines

    return []


def _extract_text_lines_with_nested_fallback(
    ocr_result: Any,
) -> list[dict[str, Any]]:
    lines = extract_text_lines(ocr_result)
    nested_lines: list[dict[str, Any]] = []

    if isinstance(ocr_result, dict):
        results = ocr_result.get("results")
        if isinstance(results, list):
            for item in results:
                if isinstance(item, dict) and isinstance(item.get("lines"), list):
                    nested_lines.extend(extract_text_lines({"lines": item["lines"]}))

    if not nested_lines:
        return lines

    if not lines:
        return nested_lines

    seen_keys = {
        (line.get("text"), json.dumps(line.get("bbox"), ensure_ascii=False))
        for line in lines
    }
    for line in nested_lines:
        key = (line.get("text"), json.dumps(line.get("bbox"), ensure_ascii=False))
        if key in seen_keys:
            continue
        lines.append(line)
    return lines


def _build_ocr_config(model: str) -> OCRConfig:
    settings = get_settings()
    return OCRConfig(
        job_url=settings.PADDLEOCR_JOB_URL,
        token=(
            settings.PADDLEOCR_TOKEN.get_secret_value()
            if hasattr(settings.PADDLEOCR_TOKEN, "get_secret_value")
            else settings.PADDLEOCR_TOKEN
        ),
        model=model,
        lang="ch",
        use_angle_cls=True,
        det=True,
        rec=True,
        det_db_box_thresh=settings.PADDLEOCR_DET_DB_BOX_THRESH,
        det_db_unclip_ratio=settings.PADDLEOCR_DET_DB_UNCLIP_RATIO,
        rec_char_type="ch",
        device="cpu",
        use_doc_orientation_classify=settings.PADDLEOCR_USE_DOC_ORIENTATION_CLASSIFY,
        use_doc_unwarping=settings.PADDLEOCR_USE_DOC_UNWARPING,
        use_textline_orientation=settings.PADDLEOCR_USE_TEXTLINE_ORIENTATION,
        use_table_recognition=settings.PADDLEOCR_USE_TABLE_RECOGNITION,
        use_e2e_wired_table_rec_model=settings.PADDLEOCR_USE_E2E_WIRED_TABLE_REC_MODEL,
        use_e2e_wireless_table_rec_model=settings.PADDLEOCR_USE_E2E_WIRELESS_TABLE_REC_MODEL,
        use_formula_recognition=False,
        use_chart_recognition=False,
        text_det_limit_side_len=settings.PADDLEOCR_TEXT_DET_LIMIT_SIDE_LEN,
        text_det_limit_type=settings.PADDLEOCR_TEXT_DET_LIMIT_TYPE,
        text_det_thresh=settings.PADDLEOCR_TEXT_DET_THESH,
        poll_interval_s=settings.PADDLEOCR_POLL_INTERVAL_S,
        poll_timeout_s=settings.PADDLEOCR_POLL_TIMEOUT_S,
        request_timeout_s=settings.PADDLEOCR_REQUEST_TIMEOUT_S,
    )


def _get_ocr_engine() -> PaddleOCR:
    settings = get_settings()
    config = _build_ocr_config(settings.PADDLEOCR_MODEL)
    cache_key = json.dumps(asdict(config), ensure_ascii=False, sort_keys=True)
    if cache_key not in _ENGINE_CACHE:
        with _engine_lock:
            if cache_key not in _ENGINE_CACHE:
                _ENGINE_CACHE[cache_key] = PaddleOCR(config)
    return _ENGINE_CACHE[cache_key]


def _get_nutrition_ocr_engine() -> PaddleOCR:
    settings = get_settings()
    config = _build_ocr_config(settings.PADDLEOCR_NUTRITION_MODEL)
    cache_key = json.dumps(asdict(config), ensure_ascii=False, sort_keys=True)
    if cache_key not in _ENGINE_CACHE:
        with _engine_lock:
            if cache_key not in _ENGINE_CACHE:
                _ENGINE_CACHE[cache_key] = PaddleOCR(config)
    return _ENGINE_CACHE[cache_key]


def warmup() -> None:
    _get_ocr_engine()
    _get_nutrition_ocr_engine()


def recognize_full_text(image_bytes: bytes) -> OCRTextResult:
    engine = _get_ocr_engine()
    try:
        prepared_bytes = _prepare_image_for_remote_ocr(image_bytes)
        raw_result = engine.ocr(prepared_bytes)
        lines = _extract_text_lines_with_nested_fallback(raw_result)
        raw_text = "\n".join(line["text"] for line in lines if line["text"])
        result = OCRTextResult(
            raw_text=raw_text,
            lines=lines,
            blocks=[],
            source="ocr_runtime",
        )
        logger.info("ocr_full_completed", lines=len(lines))
        return result
    except Exception as exc:
        logger.warning("ocr_runtime_failed", error=str(exc))
        raise OCRServiceError("OCR runtime failed") from exc


def _extract_table_from_layout(layout_results: list[Any]) -> dict[str, Any] | None:
    for layout in layout_results:
        if not isinstance(layout, dict):
            continue

        pruned = layout.get("prunedResult", {})
        parsing_list = pruned.get("parsing_res_list", [])

        for block in parsing_list:
            if not isinstance(block, dict):
                continue
            label = block.get("block_label", "").lower()
            if label != "table":
                continue

            content = block.get("block_content", "")
            if isinstance(content, str) and "<table" in content.lower():
                return {"html": content, "source": "layout"}

            if isinstance(content, dict):
                table_html = content.get("html") or content.get("table")
                if table_html:
                    return {"html": table_html, "source": "layout"}
    return None


def _extract_table_from_html_fallback(html_text: str) -> dict[str, Any] | None:
    if "<table" not in html_text.lower() or "</table>" not in html_text.lower():
        return None

    rows = _html_table_to_structured(html_text)
    if rows:
        return {"html": html_text, "source": "html_fallback", "rows": rows}
    return None


def _html_table_to_structured(html_content: str) -> list[list[str]]:
    import re

    rows: list[list[str]] = []

    cell_pattern = re.compile(r"<td[^>]*>(.*?)</td>", re.IGNORECASE | re.DOTALL)
    row_pattern = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)

    for row_match in row_pattern.finditer(html_content):
        row_text = row_match.group(1)
        cells: list[str] = []
        for td_match in cell_pattern.finditer(row_text):
            cell_html = td_match.group(1)
            cell_text = re.sub(r"<[^>]+>", "", cell_html).strip()
            cell_text = cell_text.replace("\n", " ").replace("\r", " ")
            cell_text = " ".join(cell_text.split())
            if cell_text:
                cells.append(cell_text)
        if cells:
            rows.append(cells)

    if not rows:
        for td_match in cell_pattern.finditer(html_content):
            cell_html = td_match.group(1)
            cell_text = re.sub(r"<[^>]+>", "", cell_html).strip()
            cell_text = cell_text.replace("\n", " ").replace("\r", " ")
            cell_text = " ".join(cell_text.split())
            if cell_text:
                rows.append([cell_text])

    return rows


def _convert_table_to_nutrition_json(rows: list[list[str]]) -> dict[str, Any] | None:
    if not rows:
        return None
    return {"rows": rows}


def recognize_nutrition_table(image_bytes: bytes) -> TableRecognitionResult:
    engine = _get_nutrition_ocr_engine()
    try:
        prepared_bytes = _prepare_image_for_remote_ocr(image_bytes)
        raw_result = engine.ocr(prepared_bytes)
        lines = _extract_text_lines_with_nested_fallback(raw_result)
        raw_text = "\n".join(line["text"] for line in lines if line["text"])

        table_json = None
        table_html_url = None
        table_xlsx_url = None
        has_table = False

        layout_results = None
        if isinstance(raw_result, dict):
            results = raw_result.get("results", [])
            if results and isinstance(results[0], dict):
                layout_results = results[0].get("layoutParsingResults", [])

        if layout_results:
            table_data = _extract_table_from_layout(layout_results)
            if table_data and "html" in table_data:
                rows = _html_table_to_structured(table_data["html"])
                table_json = _convert_table_to_nutrition_json(rows)
                has_table = bool(table_json and table_json.get("rows"))
                logger.info("table_html_parsed", rows=len(rows), has_table=has_table)

        if not has_table and raw_text and "<table" in raw_text.lower():
            table_data = _extract_table_from_html_fallback(raw_text)
            if table_data and "rows" in table_data:
                table_json = _convert_table_to_nutrition_json(table_data["rows"])
                has_table = bool(table_json and table_json.get("rows"))
                logger.info(
                    "table_from_fallback_parsed",
                    rows=len(table_data["rows"]),
                    has_table=has_table,
                )

        logger.info(
            "table_recognition_debug",
            has_table=has_table,
            raw_text_len=len(raw_text) if raw_text else 0,
        )

        result = TableRecognitionResult(
            table_json=table_json,
            table_html_url=table_html_url,
            table_xlsx_url=table_xlsx_url,
            ocr_fallback_text=raw_text,
            source="ocr_runtime",
        )
        logger.info("table_recognition_completed", has_table=has_table)
        return result
    except Exception as exc:
        logger.warning("ocr_runtime_failed", error=str(exc))
        raise OCRServiceError("OCR runtime failed") from exc


@dataclass
class OCRParallelResult:
    full_text: OCRTextResult
    nutrition_table: TableRecognitionResult


def _run_single_ocr(image_bytes: bytes, config: OCRConfig) -> dict[str, Any]:
    client = PaddleOCRAPIClient(config)
    job_id = client._submit_job(image_bytes)
    job_data = client._poll_job(job_id)
    result_url = job_data.get("resultUrl") or {}
    json_url = result_url.get("jsonUrl") or result_url.get("jsonlUrl")
    if not json_url:
        raise RuntimeError(f"OCR 任务完成但缺少 jsonUrl: {job_data}")
    return client._download_jsonl_results(str(json_url))


def recognize_parallel(
    full_text_image_bytes: bytes,
    nutrition_image_bytes: bytes | None = None,
) -> OCRParallelResult:
    full_text_config = _get_ocr_engine().config
    nutrition_config = _get_nutrition_ocr_engine().config
    if nutrition_image_bytes is None:
        nutrition_image_bytes = full_text_image_bytes
    prepared_full_text_image_bytes = _prepare_image_for_remote_ocr(full_text_image_bytes)
    prepared_nutrition_image_bytes = _prepare_image_for_remote_ocr(
        nutrition_image_bytes
    )

    try:
        job1_result, job2_result = _run_parallel_jobs(
            prepared_full_text_image_bytes,
            prepared_nutrition_image_bytes,
            full_text_config,
            nutrition_config,
        )

        full_text_lines = _extract_text_lines_with_nested_fallback(job1_result)
        full_text_raw = "\n".join(
            line["text"] for line in full_text_lines if line["text"]
        )
        nutrition_lines = _extract_text_lines_with_nested_fallback(job2_result)
        nutrition_raw = "\n".join(
            line["text"] for line in nutrition_lines if line["text"]
        )

        nutrition_result = TableRecognitionResult(
            table_json=None,
            table_html_url=None,
            table_xlsx_url=None,
            ocr_fallback_text=nutrition_raw or full_text_raw,
            source="ocr_runtime",
        )

        layout_results = None
        if isinstance(job2_result, dict):
            results = job2_result.get("results", [])
            if results and isinstance(results[0], dict):
                layout_results = results[0].get("layoutParsingResults", [])

        table_json = None
        has_table = False

        if layout_results:
            table_data = _extract_table_from_layout(layout_results)
            if table_data and "html" in table_data:
                rows = _html_table_to_structured(table_data["html"])
                table_json = _convert_table_to_nutrition_json(rows)
                has_table = bool(table_json and table_json.get("rows"))

        if not has_table and full_text_raw and "<table" in full_text_raw.lower():
            table_data = _extract_table_from_html_fallback(full_text_raw)
            if table_data and "rows" in table_data:
                table_json = _convert_table_to_nutrition_json(table_data["rows"])
                has_table = bool(table_json and table_json.get("rows"))

        nutrition_result.table_json = table_json
        logger.info("table_recognition_completed", has_table=has_table)

        full_text_result = OCRTextResult(
            raw_text=full_text_raw,
            lines=full_text_lines,
            blocks=[],
            source="ocr_runtime",
        )
        logger.info("ocr_full_completed", lines=len(full_text_lines))

        return OCRParallelResult(
            full_text=full_text_result,
            nutrition_table=nutrition_result,
        )

    except Exception as exc:
        logger.warning("ocr_runtime_failed", error=str(exc))
        raise OCRServiceError("OCR runtime failed") from exc


def _run_parallel_jobs(
    full_text_image_bytes: bytes,
    nutrition_image_bytes: bytes,
    full_text_config: OCRConfig,
    nutrition_config: OCRConfig,
) -> tuple[dict[str, Any], dict[str, Any]]:
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future1 = executor.submit(_run_single_ocr, full_text_image_bytes, full_text_config)
        future2 = executor.submit(
            _run_single_ocr, nutrition_image_bytes, nutrition_config
        )

        job1_result = future1.result()
        job2_result = future2.result()

    return job1_result, job2_result


__all__ = [
    "OCRTextResult",
    "TableRecognitionResult",
    "OCRParallelResult",
    "recognize_full_text",
    "recognize_nutrition_table",
    "recognize_parallel",
]
