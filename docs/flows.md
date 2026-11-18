# Composable Python Flows (`flows/`)

Instead of introducing a heavy external workflow engine container (such as Node-RED or n8n), AIFactoryBox includes a zero-dependency asynchronous Python client SDK and composable pipelines under `flows/`.

## Architecture & Design Principles

- **Zero Extra Infrastructure**: Uses only `httpx` (already required by the project) and runs from the CLI, cron jobs, or external worker scripts without adding containers or RAM overhead.
- **Public Ingress Only**: `AIFactoryClient` targets Nginx (`http://localhost` by default) with a LiteLLM bearer key (`AIFACTORYBOX_API_KEY`), preserving authentication, rate limits, spend attribution, and pre-call PII guardrails.
- **Modular Pipelines**: Composes atomic gateway primitives (`to_markdown`, `ocr`, `anonymize`, `transcribe`, `synthesize`, `ingest`, `search`, `chat`) into deterministic multi-step workflows.

## Package Layout

```text
flows/
├── __init__.py
├── sdk.py                  # AIFactoryClient async wrapper
├── runner.py               # CLI entrypoint (python -m flows.runner)
└── pipelines/
    ├── __init__.py
    ├── ingest_safe.py      # Adaptive extraction (OCR/Docling) -> Presidio PII mask -> pgvector ingest
    ├── rag_assistant.py    # Tenant-filtered vector search + rerank -> grounded chat completion
    └── voice_support.py    # Audio transcription -> RAG answer -> Piper TTS synthesis
```

## CLI Usage

Configure the gateway address and bearer key via environment variables (or `--base-url` / `--api-key` flags):

```bash
export AIFACTORYBOX_BASE_URL=http://localhost
export AIFACTORYBOX_API_KEY=sk-your-virtual-key
```

### 1. Safe Document & Scan Ingestion (`ingest-safe`)

Automatically detects file type (`.png`/`.jpg`/`.tiff` via Tesseract OCR, `.txt`/`.md`/`.csv`/`.json` directly, `.pdf`/`.docx` via Docling), masks PII via `/v1/privacy/anonymize`, and indexes sanitized chunks into PostgreSQL `pgvector`:

```bash
python -m flows.runner ingest-safe   --file ./contract.pdf   --collection enterprise_docs   --tenant acme   --language it
```

### 2. Grounded RAG Q&A (`ask`)

Retrieves tenant-scoped chunks from `knowledge_db`, re-ranks them via LiteLLM (`/rerank`), and generates a source-cited answer:

```bash
python -m flows.runner ask   --collection enterprise_docs   --tenant acme   --question "Qual è la politica di reso?"   --top-k 3
```

### 3. End-to-End Voice Support (`voice-ask`)

Transcribes an audio query with Whisper, runs the RAG Q&A pipeline, and synthesizes the spoken response via Piper TTS:

```bash
python -m flows.runner voice-ask   --audio ./question.wav   --collection enterprise_docs   --tenant acme
```

## Programmatic Usage (`AIFactoryClient`)

```python
import asyncio
from pathlib import Path
from flows.sdk import AIFactoryClient
from flows.pipelines.ingest_safe import safe_ingest_pipeline
from flows.pipelines.rag_assistant import rag_answer_pipeline

async def main():
    client = AIFactoryClient(base_url="http://localhost", api_key="sk-your-key")
    await safe_ingest_pipeline(client, Path("policy.pdf"), collection="support_kb", tenant="acme")
    result = await rag_answer_pipeline(client, collection="support_kb", question="Return window?", tenant="acme")
    print(result["answer"])
    print(result["sources"])

asyncio.run(main())
```
