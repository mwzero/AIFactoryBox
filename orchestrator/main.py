from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import httpx
import os

app = FastAPI(
    title="AIFactoryBox Orchestrator",
    description="Enterprise AI Gateway Primitive API Orchestrator",
    version="1.1.0"
)

# Endpoint dei servizi backend definiti in Docker Compose
DOCLING_URL = os.getenv("DOCLING_URL", "http://engine-doc-extraction:5000/process")
PRESIDIO_ANALYZER_URL = os.getenv("PRESIDIO_ANALYZER_URL", "http://pii-presidio-analyzer:3000/analyze")
PRESIDIO_ANONYMIZER_URL = os.getenv("PRESIDIO_ANONYMIZER_URL", "http://pii-presidio-anonymizer:3000/anonymize")
WHISPER_URL = os.getenv("WHISPER_URL", "http://engine-speech-transcribe:8000/v1/audio/transcriptions")
TEI_URL = os.getenv("TEI_URL", "http://engine-vector-embeddings:80/embed")

# Nuovi endpoint backend
RERANK_URL = os.getenv("RERANK_URL", "http://engine-rerank:80/rerank")
TTS_URL = os.getenv("TTS_URL", "http://engine-tts:5500/api/tts")
GUARDRAIL_URL = os.getenv("GUARDRAIL_URL", "http://pii-guardrails:8000/v1/chat/completions")
OCR_URL = os.getenv("OCR_URL", "http://engine-vision-ocr:8080/ocr")


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

class RerankRequest(BaseModel):
    query: str = Field(..., example="Qual è la politica di reso per gli articoli difettosi?")
    documents: List[str] = Field(..., example=[
        "Gli articoli difettosi possono essere resi entro 30 giorni.",
        "Le spedizioni avvengono in 24-48 ore lavorative.",
        "Il reso è gratuito per tutti i clienti con abbonamento Premium."
    ])
    top_n: Optional[int] = Field(default=3, example=3)

class TTSRequest(BaseModel):
    text: str = Field(..., example="Benvenuto nell'Enterprise AI Gateway di AIFactoryBox.")
    voice: Optional[str] = Field(default="it_IT-riccardo-x_low", example="it_IT-riccardo-x_low")

class GuardrailRequest(BaseModel):
    prompt: str = Field(..., example="Spiega come la nostra azienda protegge i dati PII.")
    context: Optional[str] = Field(default=None, example="Istruzioni aziendali e linee guida sulla sicurezza.")


# ==========================================
# PRIMITIVE API ENDPOINTS
# ==========================================

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "AIFactoryBox Orchestrator", "version": "1.1.0"}


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
            analyzer_resp = await client.post(
                PRESIDIO_ANALYZER_URL,
                json={"text": payload.text, "language": payload.language}
            )
            if analyzer_resp.status_code != 200:
                raise HTTPException(status_code=analyzer_resp.status_code, detail=analyzer_resp.text)
            
            analyzer_results = analyzer_resp.json()

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


# 3. Speech & Audio Transcription (/v1/audio/transcribe)
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


# ==========================================
# NUOVE MICRO-PRIMITIVE API
# ==========================================

# 5. Re-Ranking (/v1/rerank)
@app.post("/v1/rerank", summary="Ri-ordina i documenti recuperati per pertinenza semantica")
async def rerank_documents(payload: RerankRequest):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                RERANK_URL,
                json={
                    "query": payload.query,
                    "texts": payload.documents,
                    "truncate": True
                }
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=f"Re-Ranking Error: {response.text}")
            
            results = response.json()
            if payload.top_n and len(results) > payload.top_n:
                results = results[:payload.top_n]
                
            return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 6. Text-to-Speech Synthesis (/v1/audio/synthesize)
@app.post("/v1/audio/synthesize", summary="Sintetizza testo in audio (TTS) con Piper")
async def synthesize_speech(payload: TTSRequest):
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                TTS_URL,
                json={"text": payload.text, "voice": payload.voice}
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=f"TTS Error: {response.text}")
            
            return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 7. AI Guardrails & Moderation (/v1/security/guardrail)
@app.post("/v1/security/guardrail", summary="Verifica la sicurezza dei prompt con Llama Guard")
async def check_guardrail(payload: GuardrailRequest):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            messages = []
            if payload.context:
                messages.append({"role": "system", "content": payload.context})
            messages.append({"role": "user", "content": payload.prompt})

            response = await client.post(
                GUARDRAIL_URL,
                json={
                    "model": "meta-llama/Llama-Guard-3-8B",
                    "messages": messages
                }
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=f"Guardrail Error: {response.text}")
            
            res_data = response.json()
            content = res_data["choices"][0]["message"]["content"]
            
            is_safe = content.strip().startswith("safe")
            return {
                "safe": is_safe,
                "raw_output": content
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 8. Vision & OCR (/v1/vision/ocr)
@app.post("/v1/vision/ocr", summary="Esegue OCR ed estrazione di testo da immagini con PaddleOCR")
async def vision_ocr(file: UploadFile = File(...)):
    try:
        content = await file.read()
        async with httpx.AsyncClient(timeout=30.0) as client:
            files = {"file": (file.filename, content, file.content_type)}
            response = await client.post(OCR_URL, files=files)
            
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=f"OCR Error: {response.text}")
            
            return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
