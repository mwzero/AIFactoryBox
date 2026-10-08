<p align="center">
  <img src="assets/logo.svg" alt="AIFactoryBox Logo" width="450">
</p>

**AIFactoryBox** is a self-hosted "in-a-box" Enterprise AI Services Gateway designed to serve, orchestrate, and secure standardized AI Micro-Primitive APIs (Document Extraction, PII Anonymization, Speech Transcription, Vector Embeddings) across enterprise applications.

---

## 🌟 Key Features

* **Anti-Vendor Lock-in**: Exposes standardized functional AI primitive endpoints independent of underlying models or providers.
* **DLP & PII Masking Pipeline**: Automatic detection and anonymization of sensitive data prior to external LLM forwarding using Microsoft Presidio.
* **Control Plane & Governance**: Rate limiting, tenant budgeting, usage quota tracking, and audit logging via LiteLLM Proxy and PostgreSQL.
* **Playground & Interactive Docs**: Web UI for business users (Open WebUI) and interactive developer API portal (Scalar UI).

---

## 🛠️ Micro-Primitive APIs

| Endpoint | Method | Input Payload | Output / Description | Backend Engine |
| :--- | :--- | :--- | :--- | :--- |
| `/v1/document/to-markdown` | `POST` | `multipart/form-data` (PDF, DOCX) | Structured Markdown preserving tables and layout | Docling (IBM) |
| `/v1/privacy/anonymize` | `POST` | `application/json` (`text`, `entities`) | Anonymized text + temporary safe mapping | Microsoft Presidio |
| `/v1/audio/transcribe` | `POST` | `multipart/form-data` (Audio/Video) | Timestamped text transcript with speaker diarization | Faster-Whisper |
| `/v1/embeddings/generate` | `POST` | `application/json` (`inputs`) | Dense/sparse vector representations | HuggingFace TEI |

---

## 📍 Service Endpoint Map

| Service | Description | Local URL |
| :--- | :--- | :--- |
| **FastAPI Orchestrator** | Primitive API Entrypoint & Router | `http://localhost:8080` |
| **Scalar UI** | Interactive API Documentation Portal | `http://localhost:7000` |
| **Open WebUI** | Conversational & RAG Playground | `http://localhost:3000` |
| **LiteLLM Proxy** | Core LLM Gateway, Auth & Quota Manager | `http://localhost:4000` |
| **Presidio Analyzer** | PII Detection Middleware | `http://localhost:5001` |
| **Docling Engine** | Document Extraction Engine | `http://localhost:5003` |
| **Faster-Whisper** | Speech Transcription Engine | `http://localhost:8000` |
| **TEI Server** | Vector Embeddings Engine | `http://localhost:8001` |

---

## 🚀 Quickstart

### Prerequisites
* Docker Engine `>= 24.0`
* Docker Compose `>= 2.20`

### Installation & Run
```bash
git clone [https://github.com/your-org/AIFactoryBox.git](https://github.com/your-org/AIFactoryBox.git)
cd AIFactoryBox
docker compose up -d
```

