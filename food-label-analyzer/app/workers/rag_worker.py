from __future__ import annotations

import re
from typing import Any

import chromadb
import httpx
import structlog

from app.core.config import get_settings
from app.core.errors import EmbeddingServiceError


logger = structlog.get_logger(__name__)
_HTTP_CLIENT: httpx.Client | None = None
_http_client_lock = None


def _get_http_client() -> httpx.Client:
    global _HTTP_CLIENT, _http_client_lock
    if _http_client_lock is None:
        import threading

        _http_client_lock = threading.Lock()

    if _HTTP_CLIENT is None:
        with _http_client_lock:
            if _HTTP_CLIENT is None:
                settings = get_settings()
                _HTTP_CLIENT = httpx.Client(timeout=float(settings.OLLAMA_EMBEDDING_TIMEOUT_S))
    return _HTTP_CLIENT


def _normalize_text(value: Any) -> str:
    import unicodedata
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _embed(text: str) -> list[float]:
    clean_text = _normalize_text(text)
    if not clean_text:
        raise EmbeddingServiceError("Embedding input is empty")

    settings = get_settings()
    endpoint = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/embed"
    payload = {
        "model": settings.OLLAMA_EMBEDDING_MODEL,
        "input": clean_text,
        "truncate": True,
    }

    try:
        client = _get_http_client()
        response = client.post(endpoint, json=payload)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as exc:
        raise EmbeddingServiceError("Ollama embedding request failed") from exc
    except ValueError as exc:
        raise EmbeddingServiceError("Ollama embedding response is not valid JSON") from exc

    embeddings = data.get("embeddings")
    if not isinstance(embeddings, list) or not embeddings:
        raise EmbeddingServiceError("Ollama embedding response is missing embeddings")

    first_vector = embeddings[0]
    if not isinstance(first_vector, list) or not first_vector:
        raise EmbeddingServiceError("Ollama embedding response contains an invalid vector")

    try:
        return [float(item) for item in first_vector]
    except (TypeError, ValueError) as exc:
        raise EmbeddingServiceError("Ollama embedding vector contains non-numeric values") from exc


def _embed_text(text: str) -> list[float]:
    return _embed(text)


def _normalize_term(term: str) -> str:
    return _normalize_text(term)


def _similarity_from_distance(distance: Any) -> float:
    try:
        score = 1.0 - float(distance)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, round(score, 4)))


def _coerce_aliases(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _extract_match_term(meta: dict[str, Any], fallback: str) -> str:
    for key in ("term", "name", "ingredient", "raw_term"):
        value = meta.get(key)
        if isinstance(value, str) and value.strip():
            return _normalize_text(value)
    return fallback


def _extract_function_category(meta: dict[str, Any]) -> str:
    for key in ("function_category", "category", "function", "type"):
        value = meta.get(key)
        if isinstance(value, str) and value.strip():
            return _normalize_text(value)
    return "unknown"


def _build_rag_match(item: dict[str, Any], term: str, index: int) -> dict[str, Any]:
    meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    normalized_term = _normalize_term(term)
    return {
        "id": str(item.get("id", "")),
        "term": _extract_match_term(meta, normalized_term),
        "normalized_term": _normalize_text(meta.get("normalized_term", normalized_term)),
        "aliases": _coerce_aliases(meta.get("aliases")),
        "function_category": _extract_function_category(meta),
        "is_primary": bool(meta.get("is_primary")) if "is_primary" in meta else index == 0,
        "similarity_score": _similarity_from_distance(item.get("distance")),
    }


def _match_quality(matches: list[dict[str, Any]]) -> str:
    if not matches:
        return "empty"
    best_score = matches[0]["similarity_score"]
    if best_score >= 0.8:
        return "high"
    return "weak"


def _get_chroma_client() -> chromadb.Client:
    settings = get_settings()
    chroma_data_path = settings.CHROMADB_PATH
    return chromadb.PersistentClient(path=str(chroma_data_path))


def _get_ingredients_collection() -> chromadb.Collection:
    settings = get_settings()
    client = _get_chroma_client()
    return client.get_collection(name=settings.CHROMADB_COLLECTION_INGREDIENTS)


def _get_standards_collection() -> chromadb.Collection:
    settings = get_settings()
    client = _get_chroma_client()
    return client.get_collection(name=settings.CHROMADB_COLLECTION_STANDARDS)


def warmup() -> None:
    _get_ingredients_collection()
    _get_standards_collection()
    current_settings = get_settings()
    if not current_settings.HEALTH_CHECK_EXTERNAL:
        return
    try:
        _embed("食品配料")
    except Exception as exc:
        logger.warning("rag_embedding_warmup_failed", error=str(exc))


def retrieve_all_ingredients(query_text: str, top_k: int = 5) -> list[dict[str, Any]]:
    if not query_text or not query_text.strip():
        return []

    try:
        collection = _get_ingredients_collection()
    except Exception as exc:
        logger.warning("chroma_collection_not_found", error=str(exc))
        return []

    try:
        query_embedding = _embed(query_text)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:
        logger.warning("chroma_query_failed", error=str(exc))
        return []

    if not results or not results.get("ids") or not results["ids"][0]:
        return []

    retrieved: list[dict[str, Any]] = []
    for idx, ingredient_id in enumerate(results["ids"][0]):
        doc = results["documents"][0][idx] if results.get("documents") else ""
        meta = results["metadatas"][0][idx] if results.get("metadatas") else {}
        distance = results["distances"][0][idx] if results.get("distances") else 1.0

        retrieved.append(
            {
                "id": ingredient_id,
                "document": doc,
                "metadata": meta,
                "distance": distance,
            }
        )

    return retrieved


def query_gb2760_by_keyword(keyword: str, top_k: int = 3) -> list[dict[str, Any]]:
    if not keyword or not keyword.strip():
        return []

    try:
        collection = _get_standards_collection()
    except Exception as exc:
        logger.warning("chroma_collection_not_found", error=str(exc))
        return []

    try:
        query_embedding = _embed(keyword)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:
        logger.warning("chroma_query_failed", error=str(exc))
        return []

    if not results or not results.get("ids") or not results["ids"][0]:
        return []

    retrieved: list[dict[str, Any]] = []
    for idx, doc_id in enumerate(results["ids"][0]):
        doc = results["documents"][0][idx] if results.get("documents") else ""
        meta = results["metadatas"][0][idx] if results.get("metadatas") else {}
        distance = results["distances"][0][idx] if results.get("distances") else 1.0

        retrieved.append(
            {
                "id": doc_id,
                "document": doc,
                "metadata": meta,
                "distance": distance,
            }
        )

    return retrieved


def retrieve_all(
    ingredient_terms: list[str],
    ingredients_text: str,
    top_k_ingredients: int = 5,
    top_k_per_term: int = 2,
) -> dict[str, Any]:
    if not ingredient_terms and not ingredients_text:
        return {
            "source_file": "chromadb",
            "ingredients_text": "",
            "items_total": 0,
            "retrieval_results": [],
        }

    normalized_terms: list[str] = []
    for term in ingredient_terms:
        normalized = _normalize_term(term)
        if normalized and normalized not in normalized_terms:
            normalized_terms.append(normalized)

    retrieval_items: list[dict[str, Any]] = []
    for term in normalized_terms[:10]:
        ingredient_matches = retrieve_all_ingredients(term, top_k=top_k_ingredients)
        standard_matches = query_gb2760_by_keyword(term, top_k=top_k_per_term)
        combined = ingredient_matches + standard_matches
        matches = [_build_rag_match(item, term, index) for index, item in enumerate(combined)]
        retrieval_items.append(
            {
                "raw_term": term,
                "normalized_term": term,
                "retrieved": bool(matches),
                "match_quality": _match_quality(matches),
                "matches": matches,
            }
        )

    if not retrieval_items and ingredients_text.strip():
        fallback_term = _normalize_term(ingredients_text)
        fallback_matches = retrieve_all_ingredients(fallback_term, top_k=top_k_ingredients)
        matches = [_build_rag_match(item, fallback_term, index) for index, item in enumerate(fallback_matches)]
        retrieval_items.append(
            {
                "raw_term": fallback_term,
                "normalized_term": fallback_term,
                "retrieved": bool(matches),
                "match_quality": _match_quality(matches),
                "matches": matches,
            }
        )

    return {
        "source_file": "chromadb",
        "ingredients_text": ingredients_text,
        "items_total": len(retrieval_items),
        "retrieval_results": retrieval_items,
    }


def check_additive_safety(
    additive_name: str,
    food_category: str | None = None,
) -> dict[str, Any]:
    retrieved = retrieve_all_ingredients(query_text=additive_name, top_k=3)

    if not retrieved:
        return {
            "additive": additive_name,
            "found": False,
            "safety_status": "unknown",
            "details": [],
        }

    details: list[dict[str, Any]] = []
    for item in retrieved:
        doc = item.get("document", "")
        meta = item.get("metadata", {})
        distance = item.get("distance", 1.0)

        details.append(
            {
                "id": item.get("id"),
                "description": doc[:500] if doc else "",
                "category": meta.get("category", ""),
                "usage_limit": meta.get("usage_limit", ""),
                "similarity_score": round(1.0 - distance, 4) if distance else 0.0,
            }
        )

    best_match = details[0] if details else {}
    safety_status = "permitted" if (best_match.get("similarity_score", 0) > 0.8) else "review_required"

    return {
        "additive": additive_name,
        "found": bool(retrieved),
        "safety_status": safety_status,
        "details": details,
    }


__all__ = [
    "retrieve_all",
    "retrieve_all_ingredients",
    "query_gb2760_by_keyword",
    "check_additive_safety",
    "warmup",
    "_get_ingredients_collection",
    "_get_standards_collection",
    "_embed",
]
