from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import chromadb
import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings


def _embed_texts(texts: list[str], base_url: str, model: str, timeout_s: float) -> list[list[float]]:
    endpoint = f"{base_url.rstrip('/')}/api/embed"
    payload = {
        "model": model,
        "input": texts,
        "truncate": True,
    }
    with httpx.Client(timeout=timeout_s) as client:
        response = client.post(endpoint, json=payload)
        response.raise_for_status()
        data = response.json()

    embeddings = data.get("embeddings")
    if not isinstance(embeddings, list) or len(embeddings) != len(texts):
        raise RuntimeError("Ollama embedding response size mismatch")

    vectors: list[list[float]] = []
    for vector in embeddings:
        if not isinstance(vector, list) or not vector:
            raise RuntimeError("Ollama embedding response contains an invalid vector")
        vectors.append([float(item) for item in vector])
    return vectors


def _build_source(document: str, metadata: dict[str, Any]) -> str:
    chunks: list[str] = []
    term = metadata.get("term") or metadata.get("name") or metadata.get("ingredient") or ""
    normalized_term = metadata.get("normalized_term") or ""
    aliases = metadata.get("aliases") or metadata.get("alias") or ""
    keywords = metadata.get("keywords") or ""
    embedding_text = metadata.get("embedding_text") or ""

    for item in (term, normalized_term, aliases, keywords, embedding_text, document):
        if isinstance(item, str) and item.strip():
            chunks.append(item.strip())
    return "\n".join(chunks) if chunks else document


def rebuild_collection(
    client: chromadb.Client,
    collection_name: str,
    base_url: str,
    model: str,
    timeout_s: float,
    batch_size: int,
) -> dict[str, Any]:
    source = client.get_collection(name=collection_name)
    payload = source.get(include=["documents", "metadatas"])
    ids = payload.get("ids") or []
    documents = payload.get("documents") or []
    metadatas = payload.get("metadatas") or []

    if not ids:
        raise RuntimeError(f"collection is empty: {collection_name}")

    try:
        client.delete_collection(collection_name)
    except Exception:
        pass

    target = client.get_or_create_collection(name=collection_name)

    total = 0
    embedding_dim: int | None = None
    for start in range(0, len(ids), batch_size):
        batch_ids = [str(item) for item in ids[start : start + batch_size]]
        batch_docs = [str(item or "") for item in documents[start : start + batch_size]]
        batch_metas: list[dict[str, Any]] = []
        batch_sources: list[str] = []
        for meta, doc in zip(metadatas[start : start + batch_size], batch_docs):
            meta_dict = meta if isinstance(meta, dict) else {}
            batch_metas.append(meta_dict)
            batch_sources.append(_build_source(doc, meta_dict))

        vectors = _embed_texts(batch_sources, base_url=base_url, model=model, timeout_s=timeout_s)
        if vectors and embedding_dim is None:
            embedding_dim = len(vectors[0])

        target.upsert(
            ids=batch_ids,
            documents=batch_docs,
            metadatas=batch_metas,
            embeddings=vectors,
        )
        total += len(batch_ids)

    return {
        "collection": collection_name,
        "count": total,
        "embedding_model": model,
        "embedding_dim": embedding_dim,
    }


def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Rebuild ChromaDB collections with Ollama embeddings.")
    parser.add_argument("--db-dir", default=str(settings.CHROMADB_PATH), help="Chroma persistence directory.")
    parser.add_argument("--ingredients-collection", default=settings.CHROMADB_COLLECTION_INGREDIENTS)
    parser.add_argument("--standards-collection", default=settings.CHROMADB_COLLECTION_STANDARDS)
    parser.add_argument("--ollama-base-url", default=settings.OLLAMA_BASE_URL)
    parser.add_argument("--ollama-model", default=settings.OLLAMA_EMBEDDING_MODEL)
    parser.add_argument("--timeout-s", type=float, default=float(settings.OLLAMA_EMBEDDING_TIMEOUT_S))
    parser.add_argument("--batch-size", type=int, default=32)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_dir = Path(args.db_dir)
    if not db_dir.exists():
        raise FileNotFoundError(f"ChromaDB dir not found: {db_dir}")

    client = chromadb.PersistentClient(path=str(db_dir))
    collections = []
    for name in (args.ingredients_collection, args.standards_collection):
        if name not in collections:
            collections.append(name)

    results = []
    for name in collections:
        results.append(
            rebuild_collection(
                client,
                collection_name=name,
                base_url=str(args.ollama_base_url),
                model=str(args.ollama_model),
                timeout_s=float(args.timeout_s),
                batch_size=max(1, int(args.batch_size)),
            )
        )

    for item in results:
        print(f"[rebuild] collection={item['collection']} count={item['count']} dim={item['embedding_dim']} model={item['embedding_model']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

