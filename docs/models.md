# Current model inventory

These are the full-stack defaults currently committed, not final recommendations or a
benchmark ranking. Model selection remains under review, especially for Italian
retrieval. Changing a model also requires verifying runtime compatibility,
resource use, license, download access and representative task quality.

| Task | Current model or engine | Selection point | Tradeoff |
| --- | --- | --- | --- |
| Chat | OpenAI `gpt-4o-mini` | LiteLLM alias `chat-small` | Cloud; requires an API key. No local chat runtime is configured. |
| Embeddings | `BAAI/bge-small-en-v1.5`, approximately 33M parameters | TEI + alias `embedding-small` | English retrieval; not an Italian embedding model. |
| Reranking | `cross-encoder/ms-marco-MiniLM-L-6-v2`, approximately 23M | TEI + alias `rerank-small` | English-oriented; multilingual quality requires evaluation. |
| Transcription | `Systran/faster-whisper-tiny`, approximately 39M | FastAPI request `model`, served by Speaches | Multilingual, CPU int8; less accurate than larger Whisper models. |
| OCR | Tesseract with `ita` and `eng` language data | Orchestrator image + request `language` | CPU, no vision LLM; limited on handwriting and complex layouts. |
| PII detection | spaCy `it_core_news_sm` and `en_core_web_sm`, plus Presidio recognizers | `presidio/nlp.yaml` | Lightweight NER, imperfect detection; default guardrail language is Italian. |
| Speech synthesis | Piper voice `it_IT-riccardo-x_low` | FastAPI request `voice` | Retained integration; voice availability and backend contract remain unverified. |
| Document conversion | Docling service | Compose + `DOCLING_URL` | Retained adapter; endpoint compatibility and model downloads remain unverified. |

TEI and Speaches use CPU images in the current Compose stack. No GPU service
reservation or hardware profile is configured. The Presidio base image may
contain a larger model even though only the configured small models are loaded;
this is not a promise of small image size. Model persistence and on-demand
lifecycle management are not yet consistently configured across engines.

## Model families are not interchangeable

EmbeddingGemma is a candidate embedding family to evaluate, not a replacement
for chat, speech or OCR. A small instruction model can handle chat, summaries,
classification and some extraction from text, with quality measured per task.
`gemma3:1b` is text-only and cannot provide image OCR or speech by itself.
Generative reranking via prompts has a different performance and API contract
from a dedicated reranker. LLM-based redaction is not equivalent to reliable PII protection.

## Minimal variant and proposed profiles

- **Minimal (implemented, real-model validation pending):** [LiteLLM + Ollama/Gemma](minimal.md), with native Python and Docker modes; no PostgreSQL or FastAPI.
- **Minimal plus:** add only dedicated small engines required for OCR, embeddings or audio.
- **GPU / hybrid:** select compatible runtimes and hardware resources, optionally using cloud providers for selected tasks.

A future catalog could describe task, language, runtime, model revision,
quantization, license and estimated resources. A management console could
check resources, download weights, start a runtime, test it and then activate a
LiteLLM alias. The minimal variant is available separately. No catalog, console, minimal-plus
or GPU profile is shipped in this branch.
