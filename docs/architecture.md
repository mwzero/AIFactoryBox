# Gateway architecture

```text
Clients → Nginx → LiteLLM ┬→ local runtimes / cloud providers
                         └→ native pass-through → FastAPI → specialized services
Open WebUI ─────→ LiteLLM
```

LiteLLM owns model APIs and forwards the specialized document, privacy, audio
and OCR APIs to FastAPI. Those APIs retain their URLs and payloads. No FastAPI
port is published by Compose and Nginx has no direct FastAPI upstream.

In the pinned Community version, native pass-through authentication requires
Enterprise. The public Nginx ingress therefore validates bearer keys via
LiteLLM `/v1/models` before forwarding specialized requests to LiteLLM. Keep
LiteLLM and FastAPI private: pass-through routes use `auth: false` internally.
This check validates the key, not specialized endpoint permissions, token
budgets or per-user pass-through accounting. Any key accepted by that check
can invoke specialized APIs. Native model routes retain their own controls.

Pass-through guardrails are opt-in; the chat PII guardrail does not automatically
redact arbitrary JSON or uploaded files. Upstream error statuses are preserved,
but error bodies use LiteLLM's error envelope. No wildcard upstream URLs are exposed.

`/docs` and `/openapi.json` now belong to LiteLLM. The specialized schema, docs
and health are available through authenticated `/specialized/openapi.json`,
`/specialized/docs` and `/specialized/health`. `/health` checks LiteLLM liveness,
not the readiness of every backend. Use a bearer-capable client to retrieve
specialized documentation; a plain browser navigation supplies no bearer key.

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
- The gateway `/openapi.json` and `/docs` are served by LiteLLM.
  Specialized schemas are under `/specialized/` and require a bearer key.

Standalone Vercel deployment (`api/index.py`) includes only FastAPI endpoints;
it does not include LiteLLM or the Tesseract executable. Use Docker for OCR.

Presidio uses small models at runtime, but its upstream base image can still
contain a larger preinstalled model. This revision reduces loaded models, not
necessarily image size. Compose excludes internal service names from the HTTP
proxy so service-to-service requests stay on the Docker network.
