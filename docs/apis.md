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

Model APIs require a LiteLLM bearer key. Specialized APIs require deployment
access controls; they do not pass through LiteLLM. Full payload schemas for the
specialized APIs are at `/openapi.json` and `/docs`.

See [API migration and model tradeoffs](architecture.md).
