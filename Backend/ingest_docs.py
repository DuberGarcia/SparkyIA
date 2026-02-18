import os
import uuid
from pathlib import Path
from typing import Iterable, List

import requests
from qdrant_client import QdrantClient
from qdrant_client.http import models as rest


def normalize_base_url(raw: str) -> str:
    return raw.strip().strip('"').strip("'").rstrip("/")


OLLAMA_BASE_URL = normalize_base_url(
    os.getenv("OLLAMA_BASE_URL", "http://172.20.1.33:11434")
)
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "asistente_corporativo")
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "documentacion_mkdocs")
DOCS_ROOT = Path(
    os.getenv("DOCS_ROOT", Path(__file__).resolve().parents[1] / "MKDocs" / "docs")
)
CHUNK_TOKENS = int(os.getenv("CHUNK_TOKENS", "200"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "32"))
RECREATE_COLLECTION = os.getenv("QDRANT_RECREATE", "true").lower() == "true"


def read_markdown_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*.md")):
        if path.is_file():
            print(f"Encontrado archivo: {path}")
            yield path


def clean_markdown(text: str) -> str:
    lines = []
    for line in text.replace("\r", "").splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            lines.append("")
            continue
        lines.append(stripped)
    return " ".join(part for part in lines if part)


def chunk_text(text: str, size: int, overlap: int) -> Iterable[str]:
    tokens = text.split()
    if not tokens:
        return
    start = 0
    while start < len(tokens):
        end = min(len(tokens), start + size)
        chunk = " ".join(tokens[start:end]).strip()
        if chunk:
            yield chunk
        if end == len(tokens):
            break
        start = max(0, end - overlap)


def extract_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("# ").strip()
    return fallback


def embed(text: str) -> List[float]:
    endpoints = ("/api/embed", "/api/embeddings")
    last_error = None
    for endpoint in endpoints:
        try:
            resp = requests.post(
                f"{OLLAMA_BASE_URL}{endpoint}",
                json={"model": OLLAMA_EMBED_MODEL, "input": text, "prompt": text},
            )
            resp.raise_for_status()
            payload = resp.json()
            if "embedding" in payload:
                return payload["embedding"]
            embeddings = payload.get("embeddings")
            if isinstance(embeddings, list) and embeddings:
                return embeddings[0]
        except requests.HTTPError as exc:
            body = exc.response.text if exc.response is not None else str(exc)
            last_error = f"{exc} | body={body}"
            continue
        except requests.RequestException as exc:
            last_error = exc
            continue
    raise RuntimeError(f"No se pudo obtener embedding desde Ollama: {last_error}")


def ensure_collection(client: QdrantClient, vector_size: int) -> None:
    if RECREATE_COLLECTION:
        client.recreate_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=rest.VectorParams(
                size=vector_size,
                distance=rest.Distance.COSINE,
            ),
        )
        return

    collections = client.get_collections().collections
    names = {collection.name for collection in collections}
    if QDRANT_COLLECTION in names:
        return
    client.create_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=rest.VectorParams(size=vector_size, distance=rest.Distance.COSINE),
    )


def ingest() -> None:
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    docs_root = DOCS_ROOT
    assert docs_root.exists(), f"No se encontró {docs_root}"
    points: List[rest.PointStruct] = []
    vector_size = None

    for path in read_markdown_files(docs_root):
        raw_text = path.read_text(encoding="utf-8")
        cleaned_text = clean_markdown(raw_text)
        if not cleaned_text:
            continue
        rel_path = path.relative_to(docs_root)
        title = extract_title(raw_text, fallback=path.stem.replace("-", " ").title())

        for idx, chunk in enumerate(chunk_text(cleaned_text, CHUNK_TOKENS, CHUNK_OVERLAP)):
            vector = embed(chunk)
            if vector_size is None:
                vector_size = len(vector)
                ensure_collection(client, vector_size)
            point_id = str(uuid.uuid4())
            payload = {
                "text": chunk,
                "source": str(rel_path),
                "chunk": idx,
                "title": title,
            }
            points.append(
                rest.PointStruct(id=point_id, vector=vector, payload=payload)
            )
            if len(points) >= BATCH_SIZE:
                client.upsert(collection_name=QDRANT_COLLECTION, points=points)
                points.clear()

    if points:
        client.upsert(collection_name=QDRANT_COLLECTION, points=points)


if __name__ == "__main__":
    ingest()
