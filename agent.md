# AIFactoryBox development guidance

Use the existing checkout. LiteLLM Proxy owns model APIs, authentication,
budgets and configured Presidio text masking. FastAPI contains only specialized
document, standalone privacy, audio and OCR adapters. Do not duplicate supported
model APIs in Python. Nginx provides the shared ingress; specialized routes do
not automatically receive LiteLLM controls.

Prefer small CPU models and document language/quality tradeoffs. Current defaults
and API migration are in docs/architecture.md. Tesseract is local to the
orchestrator container with Italian and English data. No generative vision or
Llama Guard service is configured. Never claim moderation or complete PII removal.

Run pytest, the CI fatal-error flake8 check, Compose config validation and strict
MkDocs build. Guardrail tests use local Presidio doubles and the actual pinned
LiteLLM implementation; model-adapter tests use TEI-compatible doubles. Exercise
real OCR when Tesseract is installed. These do not establish full inference-stack
readiness. Preserve TLS and artifact verification during builds.
