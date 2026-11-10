# Development and validation

Use the existing checkout in a cloud task; do not create a worktree unless
explicitly requested. For native development, use Python 3.11+; the orchestrator
image and CI use Python 3.11. Local checks have also run on Python 3.12.

## Install and run

```bash
python -m venv .venv
.venv/bin/python -m pip install -r orchestrator/requirements.txt -r requirements-dev.txt
.venv/bin/python -m pip check
```

For native OCR install Tesseract, Italian/English language data and DejaVu fonts
using your operating system's package manager. Debian/Ubuntu package names are
`tesseract-ocr`, `tesseract-ocr-ita`, `tesseract-ocr-eng` and `fonts-dejavu-core`.
The orchestrator Docker image already installs the OCR runtime and language data.

To work on specialized adapters locally:

```bash
.venv/bin/python -m uvicorn main:app --app-dir orchestrator --host 127.0.0.1 --port 8080
```

This is a local development server, not the authenticated gateway. Health and
schema work without inference engines. Backend-dependent APIs need their real
services and matching URL environment variables. Do not expose this native
server publicly. The default Compose deployment publishes no FastAPI host port.

## Checks

```bash
LITELLM_LOCAL_MODEL_COST_MAP=True .venv/bin/pytest -q
RUN_DOCKER_TESTS=1 LITELLM_LOCAL_MODEL_COST_MAP=True .venv/bin/pytest tests/test_ingress.py -q
.venv/bin/flake8 orchestrator/ tests/ --select=E9,F63,F7,F82
.venv/bin/python -m pip check
docker compose --env-file .env.example config --quiet
.venv/bin/mkdocs build --strict
```

The ordinary suite skips the Docker ingress test unless `RUN_DOCKER_TESTS=1`.
The real OCR test skips if Tesseract is absent; that skip does not validate OCR.
Presidio/model-adapter tests use local service doubles. Proxy pass-through tests
use the actual pinned LiteLLM implementation and local specialized-service
doubles. None of these tests requires a paid provider or downloads inference
weights. `LITELLM_LOCAL_MODEL_COST_MAP=True` keeps the model-price lookup local.

The Docker ingress test creates an isolated network and temporary Nginx
containers, tests key acceptance/rejection and routing, then removes them. It
requires Docker socket access and the `nginx:alpine` image (or permission to pull
it). In managed cloud tasks, use the supported command escalation if sandboxing
blocks Docker or local network tests; do not change daemon permissions or bypass
network policy.

CI is currently manually triggered by `.github/workflows/ci.yml`. It runs Python
checks and an explicit Docker ingress check, builds the orchestrator and checks
its health without starting all model services. `.github/workflows/docs.yml`
publishes MkDocs to GitHub Pages only when that workflow is explicitly run.
A local documentation build does not publish the website or change Vercel.

## Documentation preview

```bash
.venv/bin/mkdocs serve --dev-addr 127.0.0.1:8000
```

The architecture SVG lives in `docs/assets/gateway-architecture.svg` and is used
by README and MkDocs. The static landing page embeds the same diagram. Keep its
copy consistent if the request path changes.

## Validation status

The implementation branch previously completed **10 tests with the Docker check
enabled**, with real Tesseract available, plus fatal-error lint, dependency
consistency, Compose validation and a strict MkDocs build. The orchestrator image
was built and its health and Italian/English OCR exercised in the container.

This evidence verifies routing and adapters, not all model inference. The full
Compose stack, real-provider chat masking and actual embedding/reranking model
quality remain unverified. A Presidio image download was blocked by a Microsoft
CDN network restriction in the cloud environment.

The Docling adapter still targets `/process` at port 5000 with a `file` multipart
field; compatibility with the selected Docling image needs checking. The Piper
adapter targets `/api/tts` at port 5500 and expects JSON; its image, voice setup
and response contract also need checking. Do not infer that these services work
from a running container, registered API schema or FastAPI health response.

## Known limits

- Existing model choices are provisional; English retrieval models need Italian evaluation.
- Small inference models do not guarantee a small complete stack or small images.
- Only Tesseract OCR has a specialized 20 MiB check; Nginx's 100M request limit is a separate ingress limit.
- Presidio's current integration is text PII masking, not comprehensive DLP or prompt safety.
- No minimal profile, Ollama/Gemma runtime, hardware selector, model catalog or management console is implemented.
