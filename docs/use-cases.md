# Use Cases & Hands-On Recipes

These ready-to-run scenarios demonstrate how to combine **AIFactoryBox** primitives (`chat`, `embeddings`, `rerank`, `privacy`, `document`, `ocr`, `audio`, `knowledge`) and **Composable Python Flows (`flows/`)** to solve common enterprise requirements immediately after starting the stack.

All commands below assume:

```bash
export AIFACTORYBOX_BASE_URL=http://localhost
export AIFACTORYBOX_API_KEY=sk-your-generated-virtual-key
```

---

## 1. Multi-Tenant Enterprise RAG with Reranking

Isolate knowledge bases by department or customer using collections and JSONB metadata filters, while tracking token spend per virtual key in LiteLLM.

### Step 1 — Ingest company policies with tenant metadata

```bash
curl --fail-with-body "$AIFACTORYBOX_BASE_URL/v1/knowledge/ingest"   -H "Authorization: Bearer $AIFACTORYBOX_API_KEY"   -F 'collection=company_policies'   -F 'text=Remote work is permitted up to 3 days per week upon manager approval. Equipment allowance is 500 EUR per year.'   -F 'metadata={"tenant":"hr","region":"eu"}'

curl --fail-with-body "$AIFACTORYBOX_BASE_URL/v1/knowledge/ingest"   -H "Authorization: Bearer $AIFACTORYBOX_API_KEY"   -F 'collection=company_policies'   -F 'text=Production database credentials must be rotated every 90 days via Vault.'   -F 'metadata={"tenant":"security","region":"eu"}'
```

*(Note: `knowledge_db`, the `vector` extension, and the `company_policies` collection are created automatically on first request.)*

### Step 2 — Query with tenant isolation and semantic reranking

```bash
python -m flows.runner ask   --collection company_policies   --tenant hr   --question "Quanti giorni di smart working sono consentiti e qual è il budget attrezzatura?"
```

---

## 2. PII-Safe Document & Scan Ingestion (DLP Before Vector Storage)

Even though `/v1/chat/completions` applies a pre-call Presidio guardrail, enterprise compliance often requires sanitizing sensitive documents **before** storing embeddings in PostgreSQL.

### Option A — Automated CLI Flow (`ingest-safe`)

Works transparently on PDFs/DOCX (via Docling), scanned invoices/images (via local Tesseract OCR), and plain text/Markdown files:

```bash
# Create a sample document containing PII
cat <<'EOF' > /tmp/sample_contract.txt
Contratto di fornitura stipulato con Mario Rossi (email: mario.rossi@example.com, tel: +39 333 1234567).
Il pagamento avverrà tramite bonifico su IBAN IT60X0542811101000000123456 entro 30 giorni.
EOF

# Extract -> Mask PII via Presidio -> Index sanitized chunks into pgvector
python -m flows.runner ingest-safe   --file /tmp/sample_contract.txt   --collection legal_archive   --tenant legal   --language it

# Verify that stored chunks contain masked tokens (<PERSON>, <EMAIL_ADDRESS>, <IBAN_CODE>)
python -m flows.runner ask   --collection legal_archive   --tenant legal   --question "Quali sono i termini di pagamento del contratto?"
```

### Option B — Direct API Calls (`curl`)

```bash
# 1. Extract text from a scanned image via Tesseract OCR
OCR_TEXT=$(curl -sS "$AIFACTORYBOX_BASE_URL/v1/vision/ocr?language=ita%2Beng"   -H "Authorization: Bearer $AIFACTORYBOX_API_KEY"   -F 'file=@./invoice_scan.png' | python -c "import sys,json; print(json.load(sys.stdin)['result']['text'])")

# 2. Mask PII via Microsoft Presidio
CLEAN_TEXT=$(curl -sS "$AIFACTORYBOX_BASE_URL/v1/privacy/anonymize"   -H "Authorization: Bearer $AIFACTORYBOX_API_KEY"   -H 'Content-Type: application/json'   -d "$(python -c 'import json,sys; print(json.dumps({"text": sys.argv[1], "language": "it"}))' "$OCR_TEXT")"   | python -c "import sys,json; print(json.load(sys.stdin)['text'])")

# 3. Store sanitized text in Knowledge Base
curl --fail-with-body "$AIFACTORYBOX_BASE_URL/v1/knowledge/ingest"   -H "Authorization: Bearer $AIFACTORYBOX_API_KEY"   -F 'collection=legal_archive'   -F "text=$CLEAN_TEXT"   -F 'metadata={"tenant":"legal","sanitized":true}'
```

---

## 3. Multimodal Meeting & Audio Knowledge Base

Index recorded meetings or voice notes by chaining Faster-Whisper transcription with `/v1/knowledge/ingest`:

```python
import asyncio
from pathlib import Path
from flows.sdk import AIFactoryClient
from flows.pipelines.rag_assistant import rag_answer_pipeline

async def index_and_query_meeting():
    client = AIFactoryClient()
    # 1. Transcribe audio recording
    transcript = await client.transcribe(Path("weekly_sync.mp3"), language="it")
    # 2. Anonymize participant names/emails before indexing
    clean_transcript = await client.anonymize(transcript, language="it")
    # 3. Store in pgvector
    await client.ingest(
        collection="meeting_notes",
        text=clean_transcript,
        metadata={"tenant": "product", "source_file": "weekly_sync.mp3"},
    )
    # 4. Ask questions across indexed meetings
    res = await rag_answer_pipeline(
        client,
        collection="meeting_notes",
        question="Quali decisioni sono state prese sulla release?",
        tenant="product",
    )
    print(res["answer"])

asyncio.run(index_and_query_meeting())
```

---

## 4. End-to-End Voice Customer Support Assistant

Combine speech recognition, tenant-scoped RAG retrieval, LLM response generation, and Piper TTS synthesis in a single command:

```bash
python -m flows.runner voice-ask   --audio ./customer_question.wav   --collection company_policies   --tenant hr
```

---

## 5. Integrating External Agents (MCP / Markdown-Driven Agents)

Because every primitive is exposed behind a single OpenAI-compatible and REST ingress (`/v1/chat/completions`, `/v1/knowledge/search`, `/v1/privacy/anonymize`, `/v1/vision/ocr`), external agent frameworks can treat AIFactoryBox as a governed tool backend:

- Issue a dedicated LiteLLM virtual key with a strict budget and rate limit for each agent.
- Point the agent's LLM base URL to `http://localhost/v1` (automatic pre-call PII masking).
- Register `AIFactoryClient` methods (`search`, `ingest`, `ocr`, `anonymize`) as agent tools so every retrieval and model invocation is audited in PostgreSQL.
