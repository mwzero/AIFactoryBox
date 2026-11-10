# Quickstart

Requires Docker >=24, Compose >=2.20, at least 4 CPU / 8 GB RAM. The default
stack still includes Docling and Open WebUI; small inference models do not make
the entire stack small. Model downloads need access to Hugging Face and its
artifact destinations; image/build downloads need the registries, PyPI, Debian
and GitHub. Keep TLS verification enabled and provide proxy CA trust where needed.

```bash
cp .env.example .env
# Edit .env: random LITELLM_MASTER_KEY, URL-safe POSTGRES_PASSWORD;
# OPENAI_API_KEY is optional unless using chat-small.
# Leave a nonempty WEBUI_LITELLM_API_KEY placeholder until generating a key.
docker compose up -d --build
curl --fail http://localhost/health
```

Generate a LiteLLM virtual key using the administrative key from a trusted local
client. To access its management API without publishing another port:

```bash
docker compose exec litellm-proxy python -c 'import os, urllib.request; r=urllib.request.Request("http://127.0.0.1:4000/key/generate", data=b"{}", headers={"Authorization": "Bearer " + os.environ["LITELLM_MASTER_KEY"], "Content-Type": "application/json"}); print(urllib.request.urlopen(r).read().decode())'
```

Treat the returned key as a secret. Save it as `WEBUI_LITELLM_API_KEY` in `.env`
and run `docker compose up -d open-webui`. Clients use that virtual key as their
bearer token for `/v1/chat/completions`, `/v1/embeddings` and `/rerank`.
Open WebUI is at the gateway root; model API docs are at `/docs`; specialized schemas are available at
`/specialized/openapi.json` with a bearer key.

All specialized API calls also require that bearer key at the Nginx ingress.
Their paths are forwarded through LiteLLM to internal FastAPI; see
[access-control limitations](security.md).

Verify actual chat masking with non-sensitive test data and inspect a controlled
provider before production use. `/health` checks only LiteLLM liveness; it does not prove
that FastAPI, Presidio or inference models are ready. First startup downloads
models and can take several minutes.

See [Architecture](architecture.md) for model choices and breaking API changes.

## Builds behind a TLS-inspecting proxy

The two local Dockerfiles accept an optional BuildKit `proxy_ca` secret.
For example, build the orchestrator with
`docker build --secret id=proxy_ca,src=/path/to/combined-ca.pem -t aifactorybox-orchestrator ./orchestrator`.
Supply the same secret to the Presidio build. Mount the CA rather than disabling
TLS verification or copying a session certificate into image layers.
