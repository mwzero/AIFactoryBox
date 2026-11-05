# AIFactoryBox

A gateway composed of LiteLLM Proxy and a small FastAPI service for specialized
APIs. Model calls go through LiteLLM; documents, standalone anonymization,
audio and OCR use FastAPI. Nginx exposes one entry point.

See [Quickstart](docs/quickstart.md), [Architecture and small-model choices](docs/architecture.md),
[API migration](docs/apis.md), and [PII controls](docs/security.md).

## Development checks

```bash
python -m venv .venv
.venv/bin/pip install -r orchestrator/requirements.txt -r requirements-dev.txt
.venv/bin/pytest -q
.venv/bin/flake8 orchestrator/ --select=E9,F63,F7,F82
.venv/bin/mkdocs build --strict
```

Docker provides Tesseract for the OCR integration test. On a native development
machine install Tesseract plus English and Italian language data; the OCR test
is skipped if the executable is absent. Tests use local service doubles and
never call paid model providers or download inference models.
