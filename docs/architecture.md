# Architecture Overview

**AIFactoryBox** implements an enterprise-grade AI Gateway architecture organized in decoupled layers to prevent vendor lock-in, protect sensitive internal data, and enforce multi-tenant governance.

```
                      +-----------------------------+
                      |   Client Applications       |
                      |  (ERP, CRM, Web, Internal)  |
                      +--------------+--------------+
                                     |
               +---------------------+---------------------+
               |                                           |
               v                                           v
    +----------------------+                   +----------------------+
    |  FastAPI             |                   |  Open WebUI          |
    |  Orchestrator (:8080)|                   |  Chat/RAG (:3000)    |
    +----------+-----------+                   +-----------+----------+
               |                                           |
               |                                           v
               |                             +----------------------+
               |                             |  LiteLLM Proxy       |
               |                             |  Gateway (:4000)     |
               |                             +----------+-----------+
               |                                        |
               |                     +------------------+------------------+
               |                     v                                     v
               |           +-------------------+                 +-------------------+
               |           | PostgreSQL        |                 | External/Local    |
               |           | Control Plane DB  |                 | LLMs (OpenAI,     |
               |           | (:5432)           |                 | Ollama, vLLM)     |
               |           +-------------------+                 +-------------------+
               |
               +-----------------------------------+
               |                                   |
               v                                   v
+-------------------------------+   +-------------------------------+
|   Privacy & Safety Engines    |   |     Functional AI Engines     |
+-------------------------------+   +-------------------------------+
| - Presidio Analyzer (:5001)   |   | - Docling (:5003)             |
| - Presidio Anonymizer (:5002) |   | - Faster-Whisper (:8000)      |
| - Llama Guard 3 (:5004)       |   | - Piper TTS (:5500)           |
|                               |   | - TEI Embeddings (:8001)      |
|                               |   | - TEI Re-Ranking (:8002)      |
|                               |   | - PaddleOCR (:8003)           |
+-------------------------------+   +-------------------------------+
```

## Layer Description

1. **Ingress & Orchestration Layer (Port 8080)**: Powered by FastAPI, it aggregates specialized micro-primitives into unified REST interfaces, managing payload validation and async routing.
2. **Control Plane & Governance Layer (Port 4000 & 5432)**: LiteLLM Proxy backed by PostgreSQL coordinates tenant budgets, rate limits, virtual keys, and request auditing.
3. **Privacy & Security Perimeter**: Intercepts requests to mask Personally Identifiable Information (PII) before external transmission and checks prompts against safety guardrails.
4. **Specialized Inference Engines**: Lightweight containerized runtimes optimized for CPU/GPU execution for transcription, embeddings, document parsing, and vision.
