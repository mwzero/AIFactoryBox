from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
from scalar_fastapi import get_scalar_api_reference
import httpx
import os
import uvicorn

app = FastAPI(
    title="AIFactoryBox Orchestrator",
    description="Enterprise AI Gateway Primitive API Orchestrator",
    version="1.1.0",
    docs_url=None,   # Disabilita Swagger UI standard
    redoc_url=None   # Disabilita ReDoc standard
)

# Header pass-through per Nginx reverse proxy
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["*"])

# Endpoint backend definiti in docker-compose.yml
DOCLING_URL = os.getenv("DOCLING_URL", "http://engine-doc-extraction:5000/process")
PRESIDIO_ANALYZER_URL = os.getenv("PRESIDIO_ANALYZER_URL", "http://pii-presidio-analyzer:3000/analyze")
PRESIDIO_ANONYMIZER_URL = os.getenv("PRESIDIO_ANONYMIZER_URL", "http://pii-presidio-anonymizer:3000/anonymize")
WHISPER_URL = os.getenv("WHISPER_URL", "http://engine-speech-transcribe:8000/v1/audio/transcriptions")
TEI_URL = os.getenv("TEI_URL", "http://engine-vector-embeddings:80/embed")
RERANK_URL = os.getenv("RERANK_URL", "http://engine-rerank:80/rerank")
TTS_URL = os.getenv("TTS_URL", "http://engine-tts:5500/api/tts")
GUARDRAIL_URL = os.getenv("GUARDRAIL_URL", "http://pii-guardrails:8000/v1/chat/completions")
OCR_URL = os.getenv("OCR_URL", "http://engine-vision-ocr:8000/tesseract")


# ==========================================
# SCALAR INTERACTIVE API DOCS
# ==========================================

@app.get("/docs", include_in_schema=False)
async def scalar_docs():
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title=app.title,
    )


# ==========================================
# PYDANTIC SCHEMAS (V2 COMPATIBLE)
# ==========================================

class AnonymizeRequest(BaseModel):
    text: str = Field(..., examples=["Il cliente Mario Rossi ha la mail mario.rossi@example.com"])
    language: str = Field(default="it", examples=["it"])
    entities: Optional[List[str]] = Field(default=["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER"])

class EmbeddingRequest(BaseModel):
    inputs: List[str] = Field(..., examples=[["Testo per embedding 1", "Testo per embedding 2"]])
    truncate: Optional[bool] = Field(default=True)

class RerankRequest(BaseModel):
    query: str = Field(..., examples=["Qual è la politica di reso per gli articoli difettosi?"])
    documents: List[str] = Field(..., examples=[[
        "Gli articoli difettosi possono essere resi entro 30 giorni.",
        "Le spedizioni avvengono in 24-48 ore lavorative.",
        "Il reso è gratuito per tutti i clienti con abbonamento Premium."
    ]])
    top_n: Optional[int] = Field(default=3, examples=[3])

class TTSRequest(BaseModel):
    text: str = Field(..., examples=["Benvenuto nell'Enterprise AI Gateway di AIFactoryBox."])
    voice: Optional[str] = Field(default="it_IT-riccardo-x_low", examples=["it_IT-riccardo-x_low"])

class GuardrailRequest(BaseModel):
    prompt: str = Field(..., examples=["Spiega come la nostra azienda protegge i dati PII."])
    context: Optional[str] = Field(default=None, examples=["Istruzioni aziendali e linee guida sulla sicurezza."])


# ==========================================
# HEALTH & PRIMITIVE ENDPOINTS
# ==========================================

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "AIFactoryBox Orchestrator", "version": "1.1.0"}

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
        raise HTTPException(status_code=500, detail=str(e))

# 2. PII Anonymization
@app.post("/v1/privacy/anonymize", summary="Anonimizza testo e maschera entità PII")
async def anonymize_text(payload: AnonymizeRequest):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            analyzer_resp = await client.post(
                PRESIDIO_ANALYZER_URL,
                json={"text": payload.text, "language": payload.language}
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
        raise HTTPException(status_code=500, detail=str(e))

# 3. Speech Transcription
@app.post("/v1/audio/transcribe", summary="Trascrive file audio/video con Faster-Whisper")
async def transcribe_audio(
    file: UploadFile = File(...),
    model: str = Query(default="small"),
    language: Optional[str] = Query(default="it")
):
    try:
        content = await file.read()
        async with httpx.AsyncClient(timeout=120.0) as client:
            files = {"file": (file.filename, content, file.content_type)}
            data = {"model": model, "language": language}
            response = await client.post(WHISPER_URL, files=files, data=data)
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=f"Whisper Error: {response.text}")
            return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 4. Vector Embeddings
@app.post("/v1/embeddings/generate", summary="Genera vettori di embedding con TEI")
async def generate_embeddings(payload: EmbeddingRequest):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(TEI_URL, json=payload.model_dump())
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=f"TEI Error: {response.text}")
            return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 5. Semantic Re-ranking
@app.post("/v1/rerank", summary="Ri-ordina documenti recuperati per pertinenza")
async def rerank_documents(payload: RerankRequest):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                RERANK_URL,
                json={"query": payload.query, "texts": payload.documents, "truncate": True}
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=f"Re-Ranking Error: {response.text}")
            results = response.json()
            if payload.top_n and len(results) > payload.top_n:
                results = results[:payload.top_n]
            return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
        raise HTTPException(status_code=500, detail=str(e))

# 7. AI Guardrails
@app.post("/v1/security/guardrail", summary="Verifica prompt con Llama Guard")
async def check_guardrail(payload: GuardrailRequest):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            messages = []
            if payload.context:
                messages.append({"role": "system", "content": payload.context})
            messages.append({"role": "user", "content": payload.prompt})

            response = await client.post(
                GUARDRAIL_URL,
                json={"model": "meta-llama/Llama-Guard-3-8B", "messages": messages}
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=f"Guardrail Error: {response.text}")
            content = response.json()["choices"][0]["message"]["content"]
            return {"safe": content.strip().startswith("safe"), "raw_output": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 8. Vision & OCR
@app.post("/v1/vision/ocr", summary="Esegue OCR da immagini tramite microservizio OCR")
async def vision_ocr(
    file: UploadFile = File(...),
    language: Optional[str] = Query(default="ita+eng")
):
    try:
        content = await file.read()
        async with httpx.AsyncClient(timeout=45.0) as client:
            files = {"file": (file.filename, content, file.content_type)}
            response = await client.post(OCR_URL, files=files, params={"language": language})
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=f"OCR Error: {response.text}")
            return {"filename": file.filename, "result": response.json()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)