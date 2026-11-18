# API guide

Use the shared ingress, normally `http://localhost`, with a generated LiteLLM
bearer key. Do not call host ports 4000 or 8080; Compose does not publish them.
The examples assume `AIFACTORYBOX_API_KEY` was set securely as shown in
[Quickstart](quickstart.md#check-the-api-paths).

## Routes and contracts

| Method / path | Execution | Input / result |
| --- | --- | --- |
| POST `/v1/chat/completions` | LiteLLM → provider | OpenAI-compatible messages; alias `chat-small`. Supported chat text passes through the configured pre-call PII guardrail. |
| POST `/v1/embeddings` | LiteLLM → TEI | `model: embedding-small`, `input`; OpenAI-compatible embedding response. |
| POST `/rerank` or `/v1/rerank` | LiteLLM → TEI | `model: rerank-small`, `query`, `documents`, optional `top_n`; native rerank response. |
| GET `/v1/models` | LiteLLM | Available aliases, not model readiness. |
| POST `/v1/document/to-markdown` | LiteLLM pass-through → FastAPI → Docling | Multipart `file`; returns the backend JSON. Actual conversion compatibility remains unverified. |
| POST `/v1/privacy/anonymize` | LiteLLM pass-through → FastAPI → Presidio | `text`, `language` (default `it`), optional `entities`; anonymizer JSON. Independent of the chat guardrail. |
| POST `/v1/audio/transcribe` | LiteLLM pass-through → FastAPI → Speaches | Multipart `file`; query `model` defaults to `Systran/faster-whisper-tiny`, `language` to `it`; backend JSON. |
| POST `/v1/audio/synthesize` | LiteLLM pass-through → FastAPI → Piper | `text`, optional `voice`; current adapter expects JSON, not a guaranteed WAV/MP3 response. Integration remains unverified. |
| POST `/v1/vision/ocr` | LiteLLM pass-through → FastAPI → local Tesseract | Multipart `file`, optional query `language`; image text JSON, max 20 MiB. |
| GET `/v1/knowledge/collections` | LiteLLM pass-through → FastAPI → PostgreSQL (`pgvector`) | Lists active vector collections, dimensions, distance metrics, and chunk counts. |
| POST `/v1/knowledge/collections` | LiteLLM pass-through → FastAPI → PostgreSQL (`pgvector`) | JSON (`name`, `vector_size`, `distance`); creates a vector collection in `knowledge_db`. |
| DELETE `/v1/knowledge/collections/{name}` | LiteLLM pass-through → FastAPI → PostgreSQL (`pgvector`) | Deletes a vector collection and cascades chunk removal. |
| POST `/v1/knowledge/ingest` | LiteLLM pass-through → FastAPI → Docling + LiteLLM (`/v1/embeddings`) + PostgreSQL (`pgvector`) | Multipart form (`collection`, `text` or `file`, `chunk_size`, `chunk_overlap`, `metadata`). Propagates caller bearer key to LiteLLM, chunks text, embeds via `embedding-small`, and stores vectors in `knowledge_db`. |
| POST `/v1/knowledge/search` | LiteLLM pass-through → FastAPI → LiteLLM (`/v1/embeddings` + `/rerank`) + PostgreSQL (`pgvector`) | JSON (`collection`, `query`, `top_k`, `rerank`, `score_threshold`, `filter_metadata`). Performs cosine/L2/inner-product vector search with JSONB metadata filtering and optional semantic reranking via `rerank-small`. |

All operations above require a bearer key at the public gateway. Community
specialized-key validation is not fine-grained route authorization and does not
apply chat PII processing or model token budgets to general specialized requests.
However, `/v1/knowledge/ingest` and `/v1/knowledge/search` forward the caller's
bearer key to LiteLLM when calling `/v1/embeddings` and `/rerank` so embedding
and reranking usage is attributed to the caller's virtual key.
Pass-through errors retain the upstream status but use LiteLLM's error envelope.
See [Security](security.md) for the full boundary.

## Chat

This invokes the configured cloud provider and can incur charges. Use synthetic
data for initial checks. The model must not be considered safe for confidential
data until the real Presidio/provider path is verified.

```bash
curl --fail-with-body http://localhost/v1/chat/completions   -H "Authorization: Bearer $AIFACTORYBOX_API_KEY"   -H 'Content-Type: application/json'   -d '{"model":"chat-small","messages":[{"role":"user","content":"Summarize: the office opens at nine."}]}'
```

## Embeddings and reranking

```bash
curl --fail-with-body http://localhost/v1/embeddings   -H "Authorization: Bearer $AIFACTORYBOX_API_KEY"   -H 'Content-Type: application/json'   -d '{"model":"embedding-small","input":["Returns are accepted within 30 days."]}'

curl --fail-with-body http://localhost/rerank   -H "Authorization: Bearer $AIFACTORYBOX_API_KEY"   -H 'Content-Type: application/json'   -d '{"model":"rerank-small","query":"return policy","documents":["Returns within 30 days.","Shipping takes two days."],"top_n":1}'
```

Embedding results use `data[].embedding`; rerank results use `results[]` with
`index` and `relevance_score`. The current models are English-oriented; these
examples do not establish their suitability for Italian retrieval.

## Knowledge Base & RAG (`/v1/knowledge/*`)

Ingest raw text or documents (`PDF`, `DOCX`, `TXT`, `MD`) into a named collection
and retrieve ranked passages:

```bash
# 1. Ingest text with metadata (auto-creates collection if missing)
curl --fail-with-body http://localhost/v1/knowledge/ingest   -H "Authorization: Bearer $AIFACTORYBOX_API_KEY"   -F 'collection=enterprise_docs'   -F 'text=Returns are accepted within 30 days with original packaging.'   -F 'metadata={"department":"support"}'

# 2. Semantic search with metadata filter and LiteLLM reranking
curl --fail-with-body http://localhost/v1/knowledge/search   -H "Authorization: Bearer $AIFACTORYBOX_API_KEY"   -H 'Content-Type: application/json'   -d '{"collection":"enterprise_docs","query":"return policy","top_k":3,"rerank":true,"filter_metadata":{"department":"support"}}'

# 3. List or delete collections
curl --fail -H "Authorization: Bearer $AIFACTORYBOX_API_KEY"   http://localhost/v1/knowledge/collections

curl --fail -X DELETE -H "Authorization: Bearer $AIFACTORYBOX_API_KEY"   http://localhost/v1/knowledge/collections/enterprise_docs
```

## OCR

```bash
curl --fail-with-body 'http://localhost/v1/vision/ocr?language=ita%2Beng'   -H "Authorization: Bearer $AIFACTORYBOX_API_KEY"   -F 'file=@invoice.png'
```

The literal `+` must be encoded as `%2B` in a query string. Alternatively, omit
`language` to use the default `ita+eng`. The response shape is:

```json
{"filename":"invoice.png","result":{"text":"recognized text"}}
```

Supported combinations are `ita`, `eng`, `ita+eng` and `eng+ita`. Invalid or
unreadable images return 422, uploads over 20 MiB return 413 and an OCR timeout
returns 504. These error statuses are wrapped by LiteLLM at ingress. OCR does
not return structured tables, handwriting guarantees or a vision-model answer.

## Standalone anonymization

```bash
curl --fail-with-body http://localhost/v1/privacy/anonymize   -H "Authorization: Bearer $AIFACTORYBOX_API_KEY"   -H 'Content-Type: application/json'   -d '{"text":"Contatta mario@example.com","language":"it","entities":["EMAIL_ADDRESS"]}'
```

This explicitly calls Presidio through FastAPI. Chat requests do not need a
separate call to this API; LiteLLM invokes its own pre-call guardrail.

## Documentation and health

| Path | Purpose | Authentication |
| --- | --- | --- |
| `/docs`, `/openapi.json` | LiteLLM gateway documentation and registered routes; pass-through entries do not replace the detailed FastAPI schema | Served according to LiteLLM route policy |
| `/specialized/docs`, `/specialized/openapi.json` | Detailed FastAPI contracts (including `/v1/knowledge/*`) | Bearer key at Nginx |
| `/health` | LiteLLM liveness | Public |
| `/specialized/health` | FastAPI health through the gateway; does not check its engines | Bearer key at Nginx |

Obtain the detailed schema using a bearer-capable client:

```bash
curl --fail -H "Authorization: Bearer $AIFACTORYBOX_API_KEY"   http://localhost/specialized/openapi.json
```

The old `/v1/embeddings/generate` and `/v1/security/guardrail` routes are removed.
See the complete [migration table](architecture.md#migration-from-the-original-orchestrator).


## Composable Python Flows (`flows/`)

The `flows/` directory provides a lightweight async client (`flows/sdk.py`) and
ready-to-use pipelines (`flows/pipelines/`) runnable from the CLI without extra
workflow-engine containers:

```bash
# 1. Extract (Docling or Tesseract OCR), mask PII via Presidio, and ingest into pgvector
python -m flows.runner ingest-safe --file ./contract.pdf --collection enterprise_docs --tenant acme

# 2. Query the Knowledge Base with reranking and generate a grounded answer
python -m flows.runner ask --collection enterprise_docs --tenant acme --question "What is the return policy?"

# 3. End-to-end voice Q&A (Whisper transcribe -> RAG search -> chat -> Piper TTS)
python -m flows.runner voice-ask --audio ./question.wav --collection enterprise_docs --tenant acme
```
