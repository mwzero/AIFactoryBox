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


### 4. Privacy Audit & GDPR Risk Report (`pii-report`)

Scans a document or text via OCR/Docling + Presidio and produces a structured GDPR risk summary with entity counts:

```bash
python -m flows.runner pii-report --file ./customer_export.txt --language it
```

### 5. Executive Meeting Minutes (`meeting-minutes`)

Transcribes recorded meetings via Whisper, masks participant PII via Presidio, generates executive action items, and optionally indexes the minutes into `pgvector`:

```bash
python -m flows.runner meeting-minutes --audio ./board_sync.mp3 --collection meetings_kb --tenant exec
```

### 6. Killer App: Contract & Compliance Guardian (`contract-audit`)

Extracts a supplier contract (PDF/DOCX/scan), masks counterparty PII locally via Presidio, retrieves relevant company playbook clauses from `pgvector`, and produces a compliance & redlining report:

```bash
python -m flows.runner contract-audit --file ./supplier_contract.pdf --collection legal_playbook --tenant legal
```

### 7. Killer App: Invoice Zero-Touch Reconciliation (`invoice-reconcile`)

Reads an invoice or receipt (scan/PDF/text), masks PII, matches it against approved contracts/POs in `pgvector`, and flags amount or payment-term discrepancies:

```bash
python -m flows.runner invoice-reconcile --file ./invoice_scan.png --collection finance_kb --tenant finance --archive
```

*(Note: All interactive flows above can also be launched directly from the browser in the **Operations Console** at `/console/` under **3. Killer App Flows & RAG**.)*

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
