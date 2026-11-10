# APIs

| Route | Owner | Contract |
| --- | --- | --- |
| `/v1/chat/completions` | LiteLLM | OpenAI; model `chat-small` |
| `/v1/embeddings` | LiteLLM | OpenAI; model `embedding-small` |
| `/rerank`, `/v1/rerank` | LiteLLM | Native rerank; model `rerank-small` |
| `/v1/models` | LiteLLM | Available model aliases |
| `/v1/document/to-markdown` | FastAPI | Existing multipart `file` adapter |
| `/v1/privacy/anonymize` | FastAPI | `text`, `language`, optional `entities` |
| `/v1/audio/transcribe` | FastAPI | Multipart `file`; defaults to Whisper tiny |
| `/v1/audio/synthesize` | FastAPI | `text`, optional `voice` |
| `/v1/vision/ocr` | FastAPI | Multipart `file`; query `language=ita+eng`; max 20 MiB |

All public API operations require a LiteLLM bearer key. Specialized APIs pass
through LiteLLM after ingress key validation; model-specific guardrails and
budgets are not automatically applied. Specialized schemas are at
`/specialized/openapi.json` and `/specialized/docs` (bearer authentication required).
Errors preserve the upstream status but use LiteLLM's error envelope.

See [API migration and model tradeoffs](architecture.md).
