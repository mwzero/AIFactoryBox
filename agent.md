# AIFactoryBox development guidance

Use the existing checkout. LiteLLM Proxy owns model APIs, authentication,
budgets and configured Presidio text masking. FastAPI contains only specialized
document, standalone privacy, audio and OCR adapters. Do not duplicate supported
model APIs in Python. All public APIs go through LiteLLM; specialized APIs use
native pass-through. Keep LiteLLM and FastAPI private. Community pass-through
authentication is enforced at Nginx via LiteLLM /v1/models; this is key validation,
not specialized-route permissions, PII processing or model budgets. See docs/security.md.

Prefer small CPU models and document language/quality tradeoffs. Current defaults
are in docs/models.md; API migration is in docs/architecture.md. Tesseract is local to the
orchestrator container with Italian and English data. No generative vision or
Llama Guard service is configured. Never claim moderation or complete PII removal.

Run pytest, the CI fatal-error flake8 check, Compose config validation and strict
MkDocs build. Guardrail tests use local Presidio doubles and the actual pinned
LiteLLM implementation; model-adapter tests use TEI-compatible doubles. Exercise
real OCR when Tesseract is installed. These do not establish full inference-stack
readiness. Preserve TLS and artifact verification during builds.

Documentation: preserve the distinction between implemented behavior, tested
adapters and planned profiles. The README/MkDocs architecture diagram is
docs/assets/gateway-architecture.svg; website/index.html embeds the same SVG.
Keep those diagrams aligned. The static site is not a live gateway playground.

The minimal/ variant is independent of the full stack. Keep it database-free
and text-only, with no guardrail claims. Its launcher starts the standard LiteLLM
proxy and must refuse missing credentials. See minimal/README.md for modes and
known real-model validation limits.
