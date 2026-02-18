import os
from typing import List
from urllib.parse import urljoin

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from qdrant_client import QdrantClient


class Consulta(BaseModel):
    pregunta: str


def normalize_base_url(raw: str) -> str:
    return raw.strip().strip('"').strip("'").rstrip("/")


def build_ollama_url(path: str) -> str:
    return urljoin(f"{OLLAMA_BASE_URL}/", path.lstrip("/"))


QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "documentacion_mkdocs")
OLLAMA_BASE_URL = normalize_base_url(
    os.getenv("OLLAMA_BASE_URL", "http://172.20.1.33:11434")
)
OLLAMA_CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "asistente_corporativo")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "asistente_corporativo")
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "1"))
RAG_SCORE_THRESHOLD = float(os.getenv("RAG_SCORE_THRESHOLD", "0.15"))

app = FastAPI()
qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def embed_text(text: str) -> List[float]:
    endpoints = ("/api/embed", "/api/embeddings")
    last_error = None
    for endpoint in endpoints:
        try:
            resp = requests.post(
                build_ollama_url(endpoint),
                json={"model": OLLAMA_EMBED_MODEL, "input": text, "prompt": text},
            )
            resp.raise_for_status()
            payload = resp.json()
            if "embedding" in payload:
                return payload["embedding"]
            embeddings = payload.get("embeddings")
            if isinstance(embeddings, list) and embeddings:
                return embeddings[0]
            raise HTTPException(
                status_code=502,
                detail=f"Respuesta de embeddings inválida desde Ollama en {endpoint}",
            )
        except requests.HTTPError as exc:
            body = exc.response.text if exc.response is not None else str(exc)
            last_error = f"{exc} | body={body}"
            continue
        except requests.RequestException as exc:
            last_error = exc
            continue
    raise HTTPException(
        status_code=502, detail=f"No se pudo obtener el embedding desde Ollama: {last_error}"
    )


def collection_exists(collection_name: str) -> bool:
    try:
        collections = qdrant.get_collections().collections
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502, detail=f"No se pudo consultar Qdrant: {exc}"
        ) from exc
    return any(collection.name == collection_name for collection in collections)


def build_context(points) -> str:
    fragments = []
    for point in points:
        payload = point.payload or {}
        snippet = payload.get("text")
        if not snippet:
            continue
        source = payload.get("source", "desconocido")
        title = payload.get("title", "")
        if title and source:
            header = f"{title} ({source})"
        else:
            header = title or source
        fragments.append(f"{header}\n{snippet}")
    return "\n\n---\n\n".join(fragments)


def build_prompt(question: str, context: str) -> str:
    if context:
        return (
            "Responde únicamente con base en la siguiente documentación. "
            "Si la información no es suficiente explícita no respondas buscando en internet, solo puedes usar la documentacion.\n\n"
            f"Documentación:\n{context}\n\nPregunta: {question}"
        )
    return question


@app.post("/consulta")
def consultar(data: Consulta):
    pregunta = data.pregunta.strip()
    print(f"Pregunta recibida: {pregunta}")
    if not pregunta:
        raise HTTPException(status_code=400, detail="La pregunta no puede estar vacía.")
    if not collection_exists(QDRANT_COLLECTION):
        raise HTTPException(
            status_code=503,
            detail=(
                f"La colección '{QDRANT_COLLECTION}' no existe en Qdrant. "
                "Ejecuta Backend/ingest_docs.py para crearla y cargar documentos."
            ),
        )

    question_vector = embed_text(pregunta)
    try:
        query_response = qdrant.query_points(
            collection_name=QDRANT_COLLECTION,
            query=question_vector,
            limit=RAG_TOP_K,
            with_payload=True,
            score_threshold=RAG_SCORE_THRESHOLD,
        )
        print(f"Respuesta de Qdrant: {query_response}")
    except Exception as exc:  # noqa: BLE001
        print(f"Error consultando Qdrant: {exc}")
        raise HTTPException(
            status_code=502, detail=f"Error consultando Qdrant: {exc}"
        ) from exc

    matches = getattr(query_response, "points", query_response)
    context = build_context(matches)
    print(f"Contexto construido:\n{context}\n{'='*40}")
    prompt = build_prompt(pregunta, context)
    print(f"Prompt generado:\n{prompt}\n{'='*40}")
    try:
        response = requests.post(
            build_ollama_url("/api/generate"),
            json={"model": OLLAMA_CHAT_MODEL, "prompt": prompt, "stream": False},
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"Error al generar respuesta en Ollama: {exc}")
        raise HTTPException(
            status_code=502, detail=f"No se pudo generar respuesta en Ollama: {exc}"
        ) from exc

    return response.json()


@app.get("/status")
def status():
    return {"status": "ok"}
