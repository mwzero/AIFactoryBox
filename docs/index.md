# 🔌 AIFactoryBox

<p align="center">
  <strong>The Self-Hosted Enterprise AI Services Gateway & Suite</strong>
</p>

---

Welcome to the documentation for **AIFactoryBox**, an enterprise-grade "in-a-box" solution designed to orchestrate, secure, and serve functional AI Micro-Primitive APIs within your organization.

## 🌟 Key Pillars

- **Anti-Vendor Lock-in**: Standardized unified functional endpoints independent of underlying cloud or local AI providers.
- **Privacy & Compliance**: Automatic PII anonymization and DLP guardrails built into the pipeline before forwarding requests to external LLMs.
- **Enterprise Governance**: Rate limiting, tenant budgeting, usage tracking, and audit logging out-of-the-box.
- **Developer & User Playgrounds**: Comes pre-integrated with Open WebUI for end users and Scalar UI for interactive API documentation.

## 🚀 Quick Navigation

- **[Architecture Overview](architecture.md)** — Understand the proxy, orchestrator, and engine layout.
- **[Micro-Primitive APIs](apis.md)** — Detailed specification of `/v1/document/to-markdown`, `/v1/audio/transcribe`, `/v1/privacy/anonymize`, `/v1/rerank`, `/v1/vision/ocr`, and more.
- **[Quickstart & Deployment](quickstart.md)** — Get up and running with Docker Compose in under 5 minutes.
- **[Security & Guardrails](security.md)** — Learn about PII Masking with Microsoft Presidio and Llama Guard.
