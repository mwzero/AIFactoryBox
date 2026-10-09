<p align="center">
  <img src="assets/logo.svg" alt="AIFactoryBox Logo" width="450">
</p>

**AIFactoryBox** is a self-hosted "in-a-box" Enterprise AI Services Gateway designed to serve, orchestrate, and secure standardized AI Micro-Primitive APIs across enterprise applications.

## 🌟 Key Features

* **Anti-Vendor Lock-in**: Exposes standardized functional AI primitive endpoints independent of underlying models or providers.
* **DLP & PII Masking Pipeline**: Automatic detection and anonymization of sensitive data prior to external LLM forwarding using Microsoft Presidio.
* **AI Safety & Guardrails**: Real-time moderation and prompt injection detection before requests hit core models.
* **Control Plane & Governance**: Rate limiting, tenant budgeting, usage quota tracking, and audit logging via LiteLLM Proxy and PostgreSQL.
* **Playground & Interactive Docs**: Web UI for business users (Open WebUI) and interactive developer API portal (Scalar UI).

## 🛠️ Micro-Primitive APIs

| Endpoint | Method | Input Payload | Output / Description | Backend Engine |
| :--- | :--- | :--- | :--- | :--- |
| `/v1/document/to-markdown` | `POST` | `multipart/form-data` (PDF, DOCX) | Structured Markdown preserving tables and layout | Docling (IBM) |
| `/v1/document/extract-tables` | `POST` | `multipart/form-data` (PDF, Image) | Extracted structured tabular data (JSON/CSV) | Table Transformer / TATR |
| `/v1/privacy/anonymize` | `POST` | `application/json` (`text`, `entities`) | Anonymized text + temporary safe mapping | Microsoft Presidio / GliNER |
| `/v1/audio/transcribe` | `POST` | `multipart/form-data` (Audio/Video) | Timestamped text transcript with speaker diarization | Faster-Whisper |
| `/v1/audio/synthesize` | `POST` | `application/json` (`text`, `voice`) | Synthesized speech audio output (WAV/MP3) | Piper TTS / XTTS v2 |
| `/v1/embeddings/generate` | `POST` | `application/json` (`inputs`) | Dense/sparse vector representations | HuggingFace TEI |
| `/v1/rerank` | `POST` | `application/json` (`query`, `documents`) | Re-ordered document list optimized for RAG | HuggingFace TEI (BGE-Reranker) |
| `/v1/vision/ocr` | `POST` | `multipart/form-data` (Image) | Multilingual text extraction from scans and images | PaddleOCR / GOT-OCR2 |
| `/v1/security/guardrail` | `POST` | `application/json` (`prompt`, `context`) | Moderation verdict and prompt injection detection | NeMo Guardrails / Llama Guard |

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
| **TEI Embeddings & Rerank** | Vector Embeddings & Re-Ranking Engine | `http://localhost:8001` |
| **Piper TTS Engine** | Text-to-Speech Synthesis Engine | `http://localhost:8002` |
| **PaddleOCR Engine** | Vision & Optical Character Recognition Engine | `http://localhost:8003` |
| **Llama Guard Engine** | AI Guardrail & Security Engine | `http://localhost:8004` |

## 🚀 Quickstart

### Prerequisites

* Docker Engine `>= 24.0`
* Docker Compose `>= 2.20`

### Installation & Run

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-org/AIFactoryBox.git
   cd AIFactoryBox
   ```

2. **Start the infrastructure:**
   ```bash
   docker compose up -d --build
   ```

3. **Access Services:**
   * Test APIs via **Scalar UI**: http://localhost:7000
   * Access User Playground via **Open WebUI**: http://localhost:3000
   * Directly call Primitive APIs via **Orchestrator**: http://localhost:8080
