from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from pathlib import Path
import time
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from scalar_fastapi import get_scalar_api_reference
import asyncpg
import httpx
import os
import re
import uuid
import json
import logging
import uvicorn
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aifactorybox-orchestrator")

# Endpoint backend definiti in docker-compose.yml
DOCLING_URL = os.getenv("DOCLING_URL", "http://engine-doc-extraction:5000/process")
PRESIDIO_ANALYZER_URL = os.getenv("PRESIDIO_ANALYZER_URL", "http://pii-presidio-analyzer:3000/analyze")
PRESIDIO_ANONYMIZER_URL = os.getenv("PRESIDIO_ANONYMIZER_URL", "http://pii-presidio-anonymizer:3000/anonymize")
WHISPER_URL = os.getenv("WHISPER_URL", "http://engine-speech-transcribe:8000/v1/audio/transcriptions")
DEFAULT_WHISPER_MODEL = os.getenv("DEFAULT_WHISPER_MODEL", "Systran/faster-whisper-tiny")
TTS_URL = os.getenv("TTS_URL", "http://engine-tts:5500/api/tts")

# LiteLLM Proxy gateway configuration (per tracciamento audit, quote e disaccoppiamento modelli)
LITELLM_BASE_URL = os.getenv("LITELLM_BASE_URL", "http://litellm-proxy:4000").rstrip("/")
LITELLM_EMBEDDING_MODEL = os.getenv("LITELLM_EMBEDDING_MODEL", "embedding-small")
LITELLM_RERANK_MODEL = os.getenv("LITELLM_RERANK_MODEL", "rerank-small")
LITELLM_SERVICE_KEY = os.getenv("LITELLM_SERVICE_KEY", "")

KNOWLEDGE_DB_URL = os.getenv("KNOWLEDGE_DB_URL", "")
DEFAULT_VECTOR_SIZE = int(os.getenv("DEFAULT_VECTOR_SIZE", "384"))

_db_pool: Optional[asyncpg.Pool] = None

COLLECTION_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,63}$")


def validate_collection_name(name: str) -> str:
    if not COLLECTION_NAME_RE.match(name):
        raise HTTPException(
            status_code=422,
            detail="Collection name must match ^[a-zA-Z0-9_-]{1,63}$"
        )
    return name


def format_pgvector(vec: List[float]) -> str:
    return "[" + ",".join(f"{float(v):.8f}" for v in vec) + "]"


def build_litellm_headers(request: Request) -> Dict[str, str]:
    """Propaga il bearer token del chiamante a LiteLLM per audit/budget per-tenant, con fallback su service key."""
    auth_header = request.headers.get("authorization")
    if auth_header:
        return {"Authorization": auth_header, "Content-Type": "application/json"}
    if LITELLM_SERVICE_KEY:
        return {"Authorization": f"Bearer {LITELLM_SERVICE_KEY}", "Content-Type": "application/json"}
    return {"Content-Type": "application/json"}


async def ensure_knowledge_schema(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS kb_collections (
                name TEXT PRIMARY KEY,
                vector_size INTEGER NOT NULL,
                distance TEXT NOT NULL DEFAULT 'Cosine',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS kb_chunks (
                id UUID PRIMARY KEY,
                collection_name TEXT NOT NULL REFERENCES kb_collections(name) ON DELETE CASCADE,
                document_id UUID NOT NULL,
                source TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                embedding vector NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_kb_chunks_collection ON kb_chunks(collection_name);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_kb_chunks_document ON kb_chunks(document_id);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_kb_chunks_metadata ON kb_chunks USING gin(metadata);")


async def ensure_knowledge_database() -> None:
    """Crea autonomamente il database logico target (es. knowledge_db) se non esiste ancora."""
    from urllib.parse import urlparse, urlunparse
    parsed = urlparse(KNOWLEDGE_DB_URL)
    target_db = parsed.path.lstrip("/")
    if not target_db or not re.match(r"^[a-zA-Z0-9_-]{1,63}$", target_db):
        return
    admin_url = urlunparse(parsed._replace(path="/postgres"))
    conn = await asyncpg.connect(dsn=admin_url)
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", target_db)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{target_db}"')
            logger.info(f"Created PostgreSQL database '{target_db}' automatically.")
    finally:
        await conn.close()


async def get_db_pool() -> asyncpg.Pool:
    global _db_pool
    if _db_pool is not None:
        return _db_pool
    if not KNOWLEDGE_DB_URL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="KNOWLEDGE_DB_URL is not configured."
        )
    try:
        try:
            _db_pool = await asyncpg.create_pool(dsn=KNOWLEDGE_DB_URL, min_size=1, max_size=10)
        except asyncpg.InvalidCatalogNameError:
            await ensure_knowledge_database()
            _db_pool = await asyncpg.create_pool(dsn=KNOWLEDGE_DB_URL, min_size=1, max_size=10)
        await ensure_knowledge_schema(_db_pool)
        return _db_pool
    except Exception as exc:
        logger.error(f"Failed to connect to PostgreSQL knowledge store: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Knowledge database unavailable: {exc}"
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    if KNOWLEDGE_DB_URL:
        try:
            await get_db_pool()
            logger.info("Connected to PostgreSQL + pgvector knowledge store.")
        except Exception as exc:
            logger.warning(f"Knowledge DB not ready at startup (will retry lazily): {exc}")
    yield
    global _db_pool
    if _db_pool is not None:
        await _db_pool.close()
        _db_pool = None


app = FastAPI(
    title="AIFactoryBox Orchestrator",
    description="Enterprise AI Gateway Primitive API Orchestrator",
    version="1.2.0",
    docs_url=None,   # Disabilita Swagger UI standard
    redoc_url=None,  # Disabilita ReDoc standard
    lifespan=lifespan
)

# Header pass-through per Nginx reverse proxy
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["*"])


# ==========================================
# SCALAR INTERACTIVE API DOCS
# ==========================================

@app.get("/docs", include_in_schema=False)
async def scalar_docs():
    return get_scalar_api_reference(
        openapi_url=os.getenv("SCALAR_OPENAPI_URL", app.openapi_url),
        title=app.title,
    )


# ==========================================
# PYDANTIC SCHEMAS (V2 COMPATIBLE)
# ==========================================

class AnonymizeRequest(BaseModel):
    text: str = Field(..., examples=["Il cliente Mario Rossi ha la mail mario.rossi@example.com"])
    language: str = Field(default="it", examples=["it"])
    entities: Optional[List[str]] = Field(default=["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER"])

class TTSRequest(BaseModel):
    text: str = Field(..., examples=["Benvenuto nell'Enterprise AI Gateway di AIFactoryBox."])
    voice: Optional[str] = Field(default="it_IT-riccardo-x_low", examples=["it_IT-riccardo-x_low"])

class CollectionCreateRequest(BaseModel):
    name: str = Field(..., pattern="^[a-zA-Z0-9_-]{1,63}$", examples=["enterprise_docs"])
    vector_size: int = Field(default=DEFAULT_VECTOR_SIZE, ge=1, le=8192, examples=[1024])
    distance: str = Field(default="Cosine", examples=["Cosine"])

class KnowledgeSearchRequest(BaseModel):
    collection: str = Field(..., examples=["enterprise_docs"])
    query: str = Field(..., examples=["Qual è la politica di sicurezza dei dati?"])
    top_k: int = Field(default=5, ge=1, le=50)
    rerank: bool = Field(default=True, description="Ri-ordina i risultati usando il modello reranker via LiteLLM")
    score_threshold: Optional[float] = Field(default=None)
    filter_metadata: Optional[Dict[str, Any]] = Field(default=None, description="Filtri chiave-valore sui metadati")


# ==========================================
# HELPERS: ERROR HANDLING & CHUNKING
# ==========================================

def handle_downstream_error(service_name: str, e: Exception):
    if isinstance(e, HTTPException):
        raise e
    if isinstance(e, httpx.TimeoutException):
        logger.error(f"Timeout calling {service_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Downstream service '{service_name}' timed out."
        )
    if isinstance(e, httpx.RequestError):
        logger.error(f"Connection error calling {service_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unable to reach downstream service '{service_name}': {str(e)}"
        )
    logger.error(f"Unexpected error in {service_name}: {e}")
    raise HTTPException(status_code=500, detail=str(e))


def chunk_text(text: str, chunk_size: int = 800, chunk_overlap: int = 120) -> List[str]:
    """Divide il testo in chunk sovrapposti rispettando i confini di paragrafo/frase."""
    cleaned = text.strip()
    if not cleaned:
        return []
    if len(cleaned) <= chunk_size:
        return [cleaned]

    chunks: List[str] = []
    start = 0
    text_len = len(cleaned)
    while start < text_len:
        end = min(start + chunk_size, text_len)
        if end < text_len:
            for sep in ("\n\n", "\n", ". ", " "):
                idx = cleaned.rfind(sep, start + int(chunk_size * 0.5), end)
                if idx != -1:
                    end = idx + len(sep)
                    break
        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= text_len:
            break
        start = max(end - chunk_overlap, start + 1)
    return chunks


# ==========================================
# HEALTH & PRIMITIVE ENDPOINTS
# ==========================================

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "AIFactoryBox Orchestrator", "version": "1.2.0"}

CONSOLE_HTML_PATH = Path(__file__).resolve().parent / "console.html"


@app.get("/console", include_in_schema=False, response_class=HTMLResponse)
@app.get("/console/", include_in_schema=False, response_class=HTMLResponse)
async def operations_console():
    if not CONSOLE_HTML_PATH.is_file():
        raise HTTPException(status_code=404, detail="Operations console asset not found")
    return HTMLResponse(content=CONSOLE_HTML_PATH.read_text(encoding="utf-8"))


async def _probe_http(client: httpx.AsyncClient, url: str) -> Dict[str, Any]:
    start = time.perf_counter()
    try:
        resp = await client.get(url)
        latency = round((time.perf_counter() - start) * 1000, 1)
        if resp.status_code < 500:
            return {"status": "ok", "detail": f"Reachable (HTTP {resp.status_code})", "latency_ms": latency}
        return {"status": "degraded", "detail": f"HTTP {resp.status_code}", "latency_ms": latency}
    except Exception as exc:
        latency = round((time.perf_counter() - start) * 1000, 1)
        return {"status": "unreachable", "detail": str(exc), "latency_ms": latency}


@app.get("/status", summary="Verifica lo stato di readiness dei servizi e dei motori interni")
async def stack_status():
    services: Dict[str, Any] = {
        "orchestrator": {"status": "ok", "detail": "FastAPI v1.2.0 active", "latency_ms": 0.0}
    }

    # Probe PostgreSQL + pgvector
    start_db = time.perf_counter()
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            col_count = await conn.fetchval("SELECT COUNT(*) FROM kb_collections")
            chunk_count = await conn.fetchval("SELECT COUNT(*) FROM kb_chunks")
        services["postgres_pgvector"] = {
            "status": "ok",
            "detail": f"Connected ({col_count} collections, {chunk_count} chunks)",
            "latency_ms": round((time.perf_counter() - start_db) * 1000, 1),
        }
    except Exception as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        services["postgres_pgvector"] = {
            "status": "unreachable",
            "detail": str(detail),
            "latency_ms": round((time.perf_counter() - start_db) * 1000, 1),
        }

    # Probe internal HTTP backends concurrently
    from urllib.parse import urlparse
    def base_of(u: str) -> str:
        p = urlparse(u)
        return f"{p.scheme}://{p.netloc}"

    targets = {
        "litellm_proxy": f"{LITELLM_BASE_URL}/health/liveliness",
        "presidio_analyzer": f"{base_of(PRESIDIO_ANALYZER_URL)}/health",
        "presidio_anonymizer": f"{base_of(PRESIDIO_ANONYMIZER_URL)}/health",
        "docling": f"{base_of(DOCLING_URL)}/health",
        "piper_tts": f"{base_of(TTS_URL)}/",
    }
    if WHISPER_URL.startswith(LITELLM_BASE_URL):
        services["whisper_transcription"] = {
            "status": "ok",
            "detail": f"SaaS via LiteLLM ({DEFAULT_WHISPER_MODEL})",
            "latency_ms": 0.0,
        }
    else:
        targets["whisper_speaches"] = f"{base_of(WHISPER_URL)}/health"

    async with httpx.AsyncClient(timeout=3.0, trust_env=False) as client:
        results = await asyncio.gather(*(_probe_http(client, u) for u in targets.values()))
        for name, probe_res in zip(targets.keys(), results):
            services[name] = probe_res

    overall = "ok" if all(s["status"] == "ok" for s in services.values()) else "degraded"
    return {"status": overall, "services": services}


# 1. Document Extraction
@app.post("/v1/document/to-markdown", summary="Converte documenti (PDF, DOCX) in Markdown")
async def document_to_markdown(file: UploadFile = File(...)):
    try:
        content = await file.read()
        async with httpx.AsyncClient(timeout=60.0) as client:
            files = {"file": (file.filename, content, file.content_type)}
            response = await client.post(DOCLING_URL, files=files)
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=f"Docling Error: {response.text}")
            return response.json()
    except Exception as e:
        handle_downstream_error("Docling", e)

# 2. PII Anonymization
@app.post("/v1/privacy/anonymize", summary="Anonimizza testo e maschera entità PII")
async def anonymize_text(payload: AnonymizeRequest):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            analyzer_resp = await client.post(
                PRESIDIO_ANALYZER_URL,
                json={"text": payload.text, "language": payload.language, "entities": payload.entities}
            )
            if analyzer_resp.status_code != 200:
                raise HTTPException(status_code=analyzer_resp.status_code, detail=analyzer_resp.text)
            
            anonymizer_payload = {
                "text": payload.text,
                "anonymizers": {},
                "analyzer_results": analyzer_resp.json()
            }
            anonymizer_resp = await client.post(PRESIDIO_ANONYMIZER_URL, json=anonymizer_payload)
            if anonymizer_resp.status_code != 200:
                raise HTTPException(status_code=anonymizer_resp.status_code, detail=anonymizer_resp.text)
            return anonymizer_resp.json()
    except Exception as e:
        handle_downstream_error("Presidio", e)

# 3. Speech Transcription (Locale Speaches oppure SaaS Groq Whisper via LiteLLM)
@app.post("/v1/audio/transcribe", summary="Trascrive file audio/video con Whisper (locale o SaaS via LiteLLM)")
async def transcribe_audio(
    request: Request,
    file: UploadFile = File(...),
    model: Optional[str] = Query(default=None),
    language: Optional[str] = Query(default="it")
):
    resolved_model = model or DEFAULT_WHISPER_MODEL
    headers = {}
    if WHISPER_URL.startswith(LITELLM_BASE_URL):
        auth = build_litellm_headers(request).get("Authorization")
        if auth:
            headers["Authorization"] = auth
    try:
        content = await file.read()
        async with httpx.AsyncClient(timeout=120.0) as client:
            files = {"file": (file.filename, content, file.content_type)}
            data = {"model": resolved_model, "language": language}
            response = await client.post(WHISPER_URL, headers=headers, files=files, data=data)
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=f"Whisper Error: {response.text}")
            return response.json()
    except Exception as e:
        handle_downstream_error("Whisper", e)

# 6. Text-to-Speech (TTS)
@app.post("/v1/audio/synthesize", summary="Sintetizza testo in audio con Piper")
async def synthesize_speech(payload: TTSRequest):
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(TTS_URL, json={"text": payload.text, "voice": payload.voice})
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=f"TTS Error: {response.text}")
            return response.json()
    except Exception as e:
        handle_downstream_error("Piper TTS", e)

# 8. Vision & OCR
@app.post("/v1/vision/ocr", summary="Esegue OCR locale con Tesseract (italiano/inglese)")
async def vision_ocr(
    file: UploadFile = File(...),
    language: Optional[str] = Query(default="ita+eng")
):
    if language not in {"ita", "eng", "ita+eng", "eng+ita"}:
        raise HTTPException(status_code=422, detail="Supported languages: ita, eng, ita+eng")
    content = await file.read(20 * 1024 * 1024 + 1)
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image exceeds 20 MiB")
    process = await asyncio.create_subprocess_exec(
        "tesseract", "stdin", "stdout", "-l", language,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        text, _ = await asyncio.wait_for(process.communicate(content), timeout=45)
    except asyncio.TimeoutError:
        process.kill()
        await process.communicate()
        raise HTTPException(status_code=504, detail="OCR timed out")
    if process.returncode:
        raise HTTPException(status_code=422, detail="Tesseract could not read this image")
    return {"filename": file.filename, "result": {"text": text.decode("utf-8")}}


# ==========================================
# KNOWLEDGE BASE PRIMITIVES (/v1/knowledge/* - LiteLLM + pgvector)
# ==========================================

@app.get("/v1/knowledge/collections", summary="Elenca le collection nella Knowledge Base (pgvector)")
async def list_collections():
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT c.name, c.vector_size, c.distance, c.created_at, COUNT(k.id) AS chunks_count
                FROM kb_collections c
                LEFT JOIN kb_chunks k ON k.collection_name = c.name
                GROUP BY c.name, c.vector_size, c.distance, c.created_at
                ORDER BY c.created_at DESC
                """
            )
            return {
                "collections": [
                    {
                        "name": r["name"],
                        "vector_size": r["vector_size"],
                        "distance": r["distance"],
                        "chunks_count": r["chunks_count"],
                        "created_at": r["created_at"].isoformat()
                    }
                    for r in rows
                ]
            }
    except Exception as e:
        handle_downstream_error("PostgreSQL pgvector", e)


@app.post("/v1/knowledge/collections", summary="Crea una nuova collection vettoriale su PostgreSQL")
async def create_collection(payload: CollectionCreateRequest):
    validate_collection_name(payload.name)
    if payload.distance not in {"Cosine", "L2", "InnerProduct"}:
        raise HTTPException(status_code=422, detail="Supported distances: Cosine, L2, InnerProduct")
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO kb_collections (name, vector_size, distance)
                VALUES ($1, $2, $3)
                ON CONFLICT (name) DO NOTHING
                """,
                payload.name,
                payload.vector_size,
                payload.distance
            )
            return {"status": "created", "collection": payload.name, "vector_size": payload.vector_size}
    except Exception as e:
        handle_downstream_error("PostgreSQL pgvector", e)


@app.delete("/v1/knowledge/collections/{collection_name}", summary="Elimina una collection dalla Knowledge Base")
async def delete_collection(collection_name: str):
    validate_collection_name(collection_name)
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            result = await conn.execute("DELETE FROM kb_collections WHERE name = $1", collection_name)
            if result == "DELETE 0":
                raise HTTPException(status_code=404, detail=f"Collection '{collection_name}' not found")
            return {"status": "deleted", "collection": collection_name}
    except Exception as e:
        handle_downstream_error("PostgreSQL pgvector", e)


@app.post("/v1/knowledge/ingest", summary="Ingerisce documenti/testo tramite LiteLLM Embeddings e pgvector")
async def ingest_knowledge(
    request: Request,
    collection: str = Form(..., description="Nome della collection di destinazione"),
    text: Optional[str] = Form(default=None, description="Testo grezzo da indicizzare"),
    file: Optional[UploadFile] = File(default=None, description="File PDF/DOCX/TXT/MD da estrarre e indicizzare"),
    chunk_size: int = Form(default=800, ge=100, le=4000),
    chunk_overlap: int = Form(default=120, ge=0, le=1000),
    metadata: Optional[str] = Form(default=None, description="Metadati JSON opzionali associati ai chunk")
):
    validate_collection_name(collection)
    if not text and not file:
        raise HTTPException(status_code=422, detail="Fornire 'text' oppure 'file'.")

    parsed_metadata: Dict[str, Any] = {}
    if metadata:
        try:
            parsed_metadata = json.loads(metadata)
            if not isinstance(parsed_metadata, dict):
                raise ValueError("Metadata must be a JSON object")
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Invalid JSON metadata: {exc}")

    source_name = "raw_text"
    extracted_text = text or ""
    litellm_headers = build_litellm_headers(request)

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            # 1. Estrazione testo se presente file
            if file is not None:
                source_name = file.filename or "uploaded_file"
                raw_bytes = await file.read()
                if source_name.lower().endswith((".txt", ".md", ".csv", ".json")):
                    extracted_text = raw_bytes.decode("utf-8", errors="replace")
                else:
                    doc_resp = await client.post(
                        DOCLING_URL,
                        files={"file": (source_name, raw_bytes, file.content_type)}
                    )
                    if doc_resp.status_code != 200:
                        raise HTTPException(status_code=doc_resp.status_code, detail=f"Docling Error: {doc_resp.text}")
                    doc_json = doc_resp.json()
                    extracted_text = (
                        doc_json.get("document", {}).get("md_content")
                        or doc_json.get("markdown")
                        or doc_json.get("text")
                        or str(doc_json)
                    )

            # 2. Chunking
            chunks = chunk_text(extracted_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
            if not chunks:
                raise HTTPException(status_code=422, detail="Nessun contenuto testuale estratto per l'indicizzazione.")

            # 3. Generazione Embedding via LiteLLM (/v1/embeddings) per audit, spend tracking e quote
            emb_resp = await client.post(
                f"{LITELLM_BASE_URL}/v1/embeddings",
                headers=litellm_headers,
                json={"model": LITELLM_EMBEDDING_MODEL, "input": chunks}
            )
            if emb_resp.status_code != 200:
                raise HTTPException(status_code=emb_resp.status_code, detail=f"LiteLLM Embeddings Error: {emb_resp.text}")

            emb_payload = emb_resp.json()
            data_items = sorted(emb_payload.get("data", []), key=lambda item: item.get("index", 0))
            vectors = [item["embedding"] for item in data_items]
            if len(vectors) != len(chunks):
                raise HTTPException(status_code=502, detail="Invalid embedding response from LiteLLM")

        # 4. Transazione PostgreSQL: auto-creazione collection + insert batch dei chunk vettoriali
        pool = await get_db_pool()
        doc_id = uuid.uuid4()
        vector_dim = len(vectors[0])
        meta_json = json.dumps(parsed_metadata)

        async with pool.acquire() as conn:
            async with conn.transaction():
                existing = await conn.fetchrow(
                    "SELECT vector_size FROM kb_collections WHERE name = $1",
                    collection
                )
                if existing is None:
                    await conn.execute(
                        "INSERT INTO kb_collections (name, vector_size, distance) VALUES ($1, $2, 'Cosine')",
                        collection,
                        vector_dim
                    )
                elif existing["vector_size"] != vector_dim:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Vector dimension mismatch: collection expects {existing['vector_size']}, got {vector_dim}"
                    )

                records = [
                    (
                        uuid.uuid4(),
                        collection,
                        doc_id,
                        source_name,
                        idx,
                        chunk,
                        meta_json,
                        format_pgvector(vec),
                    )
                    for idx, (chunk, vec) in enumerate(zip(chunks, vectors))
                ]
                await conn.executemany(
                    """
                    INSERT INTO kb_chunks (
                        id, collection_name, document_id, source, chunk_index, content, metadata, embedding
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::vector)
                    """,
                    records
                )

        return {
            "status": "indexed",
            "collection": collection,
            "document_id": str(doc_id),
            "source": source_name,
            "chunks_indexed": len(chunks),
            "embedding_model": LITELLM_EMBEDDING_MODEL
        }
    except Exception as e:
        handle_downstream_error("Knowledge Ingest", e)


@app.post("/v1/knowledge/search", summary="Ricerca semantica via LiteLLM Embeddings, pgvector e LiteLLM Rerank")
async def search_knowledge(payload: KnowledgeSearchRequest, request: Request):
    validate_collection_name(payload.collection)
    litellm_headers = build_litellm_headers(request)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # 1. Embedding della query tramite LiteLLM (/v1/embeddings)
            emb_resp = await client.post(
                f"{LITELLM_BASE_URL}/v1/embeddings",
                headers=litellm_headers,
                json={"model": LITELLM_EMBEDDING_MODEL, "input": [payload.query]}
            )
            if emb_resp.status_code != 200:
                raise HTTPException(status_code=emb_resp.status_code, detail=f"LiteLLM Embeddings Error: {emb_resp.text}")
            query_vector = emb_resp.json()["data"][0]["embedding"]
            query_vector_str = format_pgvector(query_vector)

            # 2. Ricerca vettoriale su PostgreSQL + pgvector
            pool = await get_db_pool()
            fetch_limit = payload.top_k * 3 if payload.rerank else payload.top_k

            async with pool.acquire() as conn:
                col_row = await conn.fetchrow(
                    "SELECT distance FROM kb_collections WHERE name = $1",
                    payload.collection
                )
                if col_row is None:
                    raise HTTPException(status_code=404, detail=f"Collection '{payload.collection}' not found")

                distance = col_row["distance"]
                if distance == "L2":
                    dist_expr = "embedding <-> $1::vector"
                    score_expr = "1.0 / (1.0 + (embedding <-> $1::vector))"
                elif distance == "InnerProduct":
                    dist_expr = "embedding <#> $1::vector"
                    score_expr = "-(embedding <#> $1::vector)"
                else:  # Cosine
                    dist_expr = "embedding <=> $1::vector"
                    score_expr = "1.0 - (embedding <=> $1::vector)"

                where_clauses = ["collection_name = $2"]
                params: List[Any] = [query_vector_str, payload.collection]

                if payload.filter_metadata:
                    params.append(json.dumps(payload.filter_metadata))
                    where_clauses.append(f"metadata @> ${len(params)}::jsonb")

                if payload.score_threshold is not None:
                    params.append(payload.score_threshold)
                    where_clauses.append(f"({score_expr}) >= ${len(params)}")

                params.append(fetch_limit)
                sql = f"""
                    SELECT
                        id,
                        document_id,
                        source,
                        chunk_index,
                        content,
                        metadata,
                        ({score_expr}) AS score
                    FROM kb_chunks
                    WHERE {' AND '.join(where_clauses)}
                    ORDER BY {dist_expr} ASC
                    LIMIT ${len(params)}
                """
                rows = await conn.fetch(sql, *params)

            if not rows:
                return {"collection": payload.collection, "query": payload.query, "reranked": False, "results": []}

            candidates = []
            for r in rows:
                meta = json.loads(r["metadata"]) if isinstance(r["metadata"], str) else dict(r["metadata"] or {})
                meta.update({
                    "document_id": str(r["document_id"]),
                    "source": r["source"],
                    "chunk_index": r["chunk_index"]
                })
                candidates.append({
                    "id": str(r["id"]),
                    "score": float(r["score"]),
                    "text": r["content"],
                    "metadata": meta
                })

            # 3. Reranking semantico opzionale tramite LiteLLM (/rerank)
            if payload.rerank and len(candidates) > 1:
                texts = [c["text"] for c in candidates]
                rr_resp = await client.post(
                    f"{LITELLM_BASE_URL}/rerank",
                    headers=litellm_headers,
                    json={
                        "model": LITELLM_RERANK_MODEL,
                        "query": payload.query,
                        "documents": texts,
                        "top_n": payload.top_k
                    }
                )
                if rr_resp.status_code == 200:
                    ranked = rr_resp.json().get("results", [])
                    reordered = []
                    for item in ranked[:payload.top_k]:
                        idx = item["index"]
                        cand = candidates[idx].copy()
                        cand["rerank_score"] = item["relevance_score"]
                        reordered.append(cand)
                    return {
                        "collection": payload.collection,
                        "query": payload.query,
                        "reranked": True,
                        "results": reordered
                    }

            return {
                "collection": payload.collection,
                "query": payload.query,
                "reranked": False,
                "results": candidates[:payload.top_k]
            }
    except Exception as e:
        handle_downstream_error("Knowledge Search", e)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
