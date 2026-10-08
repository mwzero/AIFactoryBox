from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional
import httpx
import os

app = FastAPI(
    title="AIFactoryBox Orchestrator",
    description="Enterprise AI Gateway Primitive API Orchestrator",
    version="1.0.0"
)

# Endpoint dei servizi backend definiti in Docker Compose
DOCLING_URL = os.getenv("DOCLING_URL", "http://engine-doc-extraction:5000/process")
PRESIDIO_ANALYZER_URL = os.getenv("PRESIDIO_ANALYZER_URL", "http://pii-presidio-analyzer:3000/analyze")
PRESIDIO_ANONYMIZER_URL = os.getenv("PRESIDIO_ANONYMIZER_URL", "http://pii-presidio-anonymizer:3000/anonymize")
WHISPER_URL = os.getenv("WHISPER_URL", "http://engine-speech-transcribe:8000/v1/audio/transcriptions")
TEI_URL = os.getenv("TEI_URL", "http://engine-vector-embeddings:80/embed")

# ==========================================
# MODEL DEFINITIONS (PYDANTIC)
# ==========================================

class AnonymizeRequest(BaseModel):
    text: str = Field(..., example="Il cliente Mario Rossi ha la mail mario.rossi@example.com")
    language: str = Field(default="it", example="it")
    entities: Optional[List[str]] = Field(default=["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER"])

class EmbeddingRequest(BaseModel):
    inputs: List[str] = Field(..., example=["Testo per embedding 1", "Testo per embedding 2"])
    truncate: Optional[bool] = Field(default=True)

# ==========================================
# PRIMITIVE API ENDPOINTS
# ==========================================

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "AIFactoryBox Orchestrator"}

# 1. Document Extraction (/v1/document/to-markdown)
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

# 2. Privacy & Anonymization (/v1/privacy/anonymize)
@app.post("/v1/privacy/anonymize", summary="Anonimizza testo e maschera entità PII")
async def anonymize_text(payload: AnonymizeRequest):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Step 1: Analisi PII via Presidio Analyzer
            analyzer_resp = await client.post(
                PRESIDIO_ANALYZER_URL,
                json={"text": payload.text, "language": payload.language}
            )
            if analyzer_resp.status_code != 200:
                raise HTTPException(status_code=analyzer_resp.status_code, detail=analyzer_resp.text)
            
            analyzer_results = analyzer_resp.json()

            # Step 2: Anonymization via Presidio Anonymizer
            anonymizer_payload = {
                "text": payload.text,
                "anonymizers": {},
                "analyzer_results": analyzer_results
            }
            anonymizer_resp = await client.post(PRESIDIO_ANONYMIZER_URL, json=anonymizer_payload)
            if anonymizer_resp.status_code != 200:
                raise HTTPException(status_code=anonymizer_resp.status_code, detail=anonymizer_resp.text)

            return anonymizer_resp.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 3. Speech & Audio (/v1/audio/transcribe)
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

# 4. Vector & Embeddings (/v1/embeddings/generate)
@app.post("/v1/embeddings/generate", summary="Genera vettori di embedding con Text Embeddings Inference")
async def generate_embeddings(payload: EmbeddingRequest):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(TEI_URL, json=payload.model_dump())
            
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=f"TEI Error: {response.text}")
            
            return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
