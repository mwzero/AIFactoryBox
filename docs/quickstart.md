# Quickstart & Deployment Guide

Deploy AIFactoryBox in minutes using Docker Compose.

## Prerequisites

- **Docker Engine**: `>= 24.0`
- **Docker Compose**: `>= 2.20`
- Minimum Hardware: 4 vCPU, 8 GB RAM (16 GB recommended for full local model execution).

## Step-by-Step Installation

### 1. Clone Repository & Setup Environment
```bash
git clone https://github.com/mwzero/AIFactoryBox.git
cd AIFactoryBox
cp .env.example .env
```
Edit `.env` to configure your passwords and API keys:
```env
LITELLM_MASTER_KEY=sk-prod-your-secure-key
POSTGRES_PASSWORD=your_secure_db_password
OPENAI_API_KEY=sk-your-openai-key-optional
```

### 2. Start Services
```bash
docker compose up -d --build
```

### 3. Verify Health Check
```bash
curl http://localhost:8080/health
# Response: {"status":"ok","service":"AIFactoryBox Orchestrator","version":"1.1.0"}
```

### 4. Access Interfaces
- **Interactive Documentation (Scalar)**: [http://localhost:7000](http://localhost:7000)
- **Conversational Playground (Open WebUI)**: [http://localhost:3000](http://localhost:3000)
- **FastAPI OpenAPI Schema**: [http://localhost:8080/openapi.json](http://localhost:8080/openapi.json)
- **LiteLLM Admin & Proxy**: [http://localhost:4000](http://localhost:4000)
