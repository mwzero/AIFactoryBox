from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
from scalar_fastapi import get_scalar_api_reference
import httpx
import os
import uvicorn
import asyncio

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
TTS_URL = os.getenv("TTS_URL", "http://engine-tts:5500/api/tts")


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

class TTSRequest(BaseModel):
    text: str = Field(..., examples=["Benvenuto nell'Enterprise AI Gateway di AIFactoryBox."])
    voice: Optional[str] = Field(default="it_IT-riccardo-x_low", examples=["it_IT-riccardo-x_low"])

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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 3. Speech Transcription
@app.post("/v1/audio/transcribe", summary="Trascrive file audio/video con Faster-Whisper")
async def transcribe_audio(
    file: UploadFile = File(...),
    model: str = Query(default="Systran/faster-whisper-tiny"),
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
    except HTTPException:
        raise
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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 8. Vision & OCR
@app.post("/v1/vision/ocr", summary="Esegue OCR locale con Tesseract (italiano/inglese)")
async def vision_ocr(
    file: UploadFile = File(...),
    language: Optional[str] = Query(default="ita+eng")
):
    # Tesseract uses small traineddata files on CPU; no separate vision model/server.
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



if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)