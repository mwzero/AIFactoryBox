# Gateway architecture

```text
Clients / Open WebUI → Nginx → LiteLLM → Presidio → model provider
                          └→ FastAPI → document / audio services
                                    └→ local Tesseract OCR
```

LiteLLM owns `/v1/chat/completions`, `/v1/embeddings`, `/v1/models` and
`/rerank` (also `/v1/rerank`). It applies its authentication, budgets and
configured guardrails. Python no longer duplicates embedding or reranking
adapters. The standalone document, privacy, audio and OCR endpoints retain
their existing URLs. They do **not** inherit LiteLLM authentication, quotas or
PII protection. Restrict public access to these routes at deployment ingress.

## Small defaults

| Service | Default | Tradeoff |
| --- | --- | --- |
| Chat | OpenAI `gpt-4o-mini` (`chat-small`) | Cloud API; requires a key, not a local model |
| Embeddings | `BAAI/bge-small-en-v1.5` (`embedding-small`), ~33M parameters | English retrieval; not an Italian embedding model |
| Reranking | `cross-encoder/ms-marco-MiniLM-L-6-v2` (`rerank-small`), ~23M | English; smaller than BGE reranker large, lower quality on difficult/multilingual tasks |
| Transcription | `Systran/faster-whisper-tiny` via Speaches, ~39M, CPU int8 | Multilingual; lower accuracy than small |
| OCR | Tesseract, `ita` + `eng` traineddata | CPU, no generative vision model; limited on complex layouts/handwriting |
| PII NER | spaCy `it_core_news_sm` + `en_core_web_sm` | Small statistical models; detection is imperfect |
| TTS | Existing Piper `it_IT-riccardo-x_low` | Retained adapter; deployment must supply the voice |
| Documents | Existing Docling service | Not a small-model guarantee; document processing can still be heavy |

The invalid Qwen vision and unavailable Llama Guard routes were removed. There
is no content moderation or prompt-injection service in this first revision.
Tesseract returns `{"filename": "...", "result": {"text": "..."}}`; its OCR
result is now defined rather than depending on an undocumented external API.

## API migration

- `/v1/embeddings/generate` is removed. Use `/v1/embeddings` with
  `{"model":"embedding-small","input":["hello"]}` and a LiteLLM bearer key.
- `/v1/rerank` now uses LiteLLM's native contract:
  `{"model":"rerank-small","query":"returns","documents":["Returns within 30 days"],"top_n":1}`.
  The response has `results[].relevance_score` and standard LiteLLM metadata.
- `/v1/security/guardrail` is removed: its backend never existed in Compose.
- FastAPI `/openapi.json` and `/docs` describe only specialized endpoints.
  LiteLLM's internal `/openapi.json` and `/docs` describe model endpoints.

Standalone Vercel deployment (`api/index.py`) includes only FastAPI endpoints;
it does not include LiteLLM or the Tesseract executable. Use Docker for OCR.

Presidio uses small models at runtime, but its upstream base image can still
contain a larger preinstalled model. This revision reduces loaded models, not
necessarily image size. Compose excludes internal service names from the HTTP
proxy so service-to-service requests stay on the Docker network.
