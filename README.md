# AIFactoryBox (Enterprise AI Services Gateway)

**AIFactoryBox** is a self-hosted "in-a-box" solution designed to orchestrate, secure, and serve functional AI Micro-Primitive APIs (Document Extraction, PII Anonymization, Speech Transcription, Vector Embeddings) within enterprise infrastructure.

## Key Features

* **Anti-Vendor Lock-in**: Exposes standardized unified endpoints independent of underlying model providers.
* **DLP & PII Masking**: Automatic anonymization of sensitive data prior to external forwarding using Microsoft Presidio.
* **Control Plane & Governance**: Rate limiting, budget management, and tenant quota tracking powered by LiteLLM Proxy.
* **Playground & Documentation**: Interactive user interface (Open WebUI) and developer portal (Scalar UI).

## 🚀 Requirements and Quickstart

### Requirements
* Docker Engine `>= 24.0`
* Docker Compose `>= 2.20`

### Quickstart
```bash
# 1. Clone the repository
git clone [https://github.com/mwzero/AIFactoryBox.git](https://github.com/mwzero/AIFactoryBox.git)
cd AIFactoryBox
```

# 2. Start the infrastructure
```bash
docker compose up -d
```

## Service Endpoint & Interface Map
Here is the formatted Markdown table based on your data and notebook services:

| Service           | Description                                      | Local URL                   |
| ----------------- | ------------------------------------------------ | --------------------------- |
| Open WebUI        | Conversational & RAG Playground                  | `http://localhost:3000`<br> |
| LiteLLM Proxy     | Core API Gateway & Router                        | `http://localhost:4000`<br> |
| Scalar UI         | Interactive API Documentation Portal             | `http://localhost:7000`<br> |
| Presidio Analyzer | PII Masking Middleware                           | `http://localhost:5001`<br> |
| Docling Engine    | Document Extraction (`/v1/document/to-markdown`) | `http://localhost:5003`<br> |
| Faster-Whisper    | Audio Transcription (`/v1/audio/transcribe`)     | `http://localhost:8000`<br> |
| TEI Server | Vector Embeddings (`/v1/embeddings/generate`)           | `http://localhost:8001`<br> |
