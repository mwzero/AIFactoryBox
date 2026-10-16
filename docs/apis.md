# Micro-Primitive APIs Specification

AIFactoryBox exposes functional primitives under `/v1/`.

## 1. Document to Markdown
- **Endpoint**: `POST /v1/document/to-markdown`
- **Content-Type**: `multipart/form-data`
- **Parameters**: `file` (PDF, DOCX)
- **Engine**: IBM Docling (`quay.io/ds4sd/docling-serve`)
- **Description**: Extracts structural elements, layout, and tabular data into clean GitHub-Flavored Markdown.

## 2. Privacy & PII Anonymization
- **Endpoint**: `POST /v1/privacy/anonymize`
- **Content-Type**: `application/json`
- **Engine**: Microsoft Presidio Analyzer & Anonymizer
- **Payload**:
```json
{
  "text": "Il cliente Mario Rossi ha la mail mario.rossi@example.com",
  "language": "it",
  "entities": ["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER"]
}
```

## 3. Audio Transcription
- **Endpoint**: `POST /v1/audio/transcribe`
- **Content-Type**: `multipart/form-data`
- **Parameters**: `file` (Audio/Video), `model` (default: `small`), `language` (default: `it`)
- **Engine**: Faster-Whisper Server

## 4. Vector Embeddings
- **Endpoint**: `POST /v1/embeddings/generate`
- **Content-Type**: `application/json`
- **Engine**: Hugging Face Text Embeddings Inference (TEI)
- **Payload**:
```json
{
  "inputs": ["First document chunk", "Second document chunk"],
  "truncate": true
}
```

## 5. Semantic Re-Ranking
- **Endpoint**: `POST /v1/rerank`
- **Content-Type**: `application/json`
- **Engine**: Hugging Face TEI (`BAAI/bge-reranker-large`)
- **Payload**:
```json
{
  "query": "Qual è la politica di reso?",
  "documents": [
    "Gli articoli possono essere resi entro 30 giorni.",
    "Spedizioni in 24-48 ore."
  ],
  "top_n": 1
}
```

## 6. Text-to-Speech (TTS)
- **Endpoint**: `POST /v1/audio/synthesize`
- **Content-Type**: `application/json`
- **Engine**: Piper TTS
- **Payload**:
```json
{
  "text": "Benvenuto nel Gateway AIFactoryBox.",
  "voice": "it_IT-riccardo-x_low"
}
```

## 7. AI Safety & Guardrails
- **Endpoint**: `POST /v1/security/guardrail`
- **Content-Type**: `application/json`
- **Engine**: Llama Guard 3 on vLLM
- **Payload**:
```json
{
  "prompt": "Test injection string or question",
  "context": "Enterprise internal policy context"
}
```

## 8. Vision & OCR
- **Endpoint**: `POST /v1/vision/ocr`
- **Content-Type**: `multipart/form-data`
- **Parameters**: `file` (Image)
- **Engine**: PaddleOCR
