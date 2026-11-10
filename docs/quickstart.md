# Quickstart

This starts the existing full Compose stack. For the separate LiteLLM + Ollama variant, use the [minimal guide](minimal.md). Full-stack inference is not yet validated end to end;
see [validation status and known limits](development.md#validation-status).

## Prerequisites

- Docker Engine >=24 and Docker Compose >=2.20.
- CPU execution is configured. Use 4 CPU / 8 GB RAM as an initial planning baseline, not a measured readiness guarantee; Docling, WebUI, concurrent engines and model downloads can need more memory and disk.
- Network access for the container registries, Debian, PyPI, GitHub model releases and Hugging Face/model artifacts. Redirected downloads may require additional destinations.
- An OpenAI API key only if using the current `chat-small` model. There is no local chat model in this Compose configuration.
- Host port 80 available. All other services remain on the Docker network.

Use the existing checkout in a development task. For a new installation:

```bash
git clone https://github.com/mwzero/AIFactoryBox.git
cd AIFactoryBox
```

## Configure credentials

```bash
cp .env.example .env
```

Edit `.env` locally. Never commit it or paste real credentials into issue reports.

| Variable | Purpose |
| --- | --- |
| `LITELLM_MASTER_KEY` | Random administrative key beginning with `sk-`; not a general client key. |
| `POSTGRES_PASSWORD` | Random URL-safe password; it is interpolated into `DATABASE_URL`. |
| `OPENAI_API_KEY` | Required for `chat-small`; leave empty only if not making cloud chat calls. |
| `WEBUI_LITELLM_API_KEY` | A virtual key generated after LiteLLM starts. Keep the initial nonempty placeholder only during bootstrap. |

Start the stack:

```bash
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 litellm-proxy presidio-analyzer orchestrator
curl --fail http://localhost/health
```

First startup may download model weights. `depends_on` orders container starts
but does not prove application readiness. `/health` checks only LiteLLM
liveness; it is not evidence that the database, Presidio or inference engines work.

## Generate a client key

From a trusted shell on the Docker host, use the administrative key already
injected into the LiteLLM container. This prints a newly generated secret;
keep its output private. Proxy use is disabled only for this container-local call.

```bash
docker compose exec -T litellm-proxy python - <<'PYTHON'
import os
import urllib.request
request = urllib.request.Request(
    "http://127.0.0.1:4000/key/generate",
    data=b"{}",
    headers={
        "Authorization": "Bearer " + os.environ["LITELLM_MASTER_KEY"],
        "Content-Type": "application/json",
    },
)
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
print(opener.open(request).read().decode())
PYTHON
```

Save the returned key securely as `WEBUI_LITELLM_API_KEY` in `.env`, then run:

```bash
docker compose up -d open-webui
```

Open WebUI is at `http://localhost/`. It calls LiteLLM internally. Configure
virtual-key model access, budgets and limits according to your needs; those
policies are not supplied by the example key-generation request above.

## Check the API paths

Use a generated key in a bearer-capable client. The following Bash commands
read it without echoing the value and do not require sourcing `.env`:

```bash
read -r -s -p 'Client API key: ' AIFACTORYBOX_API_KEY
printf '\n'
export AIFACTORYBOX_API_KEY
curl --fail -H "Authorization: Bearer $AIFACTORYBOX_API_KEY" http://localhost/v1/models
curl --fail -H "Authorization: Bearer $AIFACTORYBOX_API_KEY" http://localhost/specialized/health
```

`/v1/models` verifies key acceptance and lists aliases, not loaded model
readiness. `/specialized/health` exercises ingress → LiteLLM → FastAPI, but
FastAPI's health handler does not check its engine dependencies. Continue with
[functional API examples](apis.md), especially OCR and a controlled chat PII test.

`/docs` and `/openapi.json` belong to LiteLLM. The specialized schema is at
`/specialized/openapi.json`. Plain browser navigation to `/specialized/docs`
does not supply a bearer key; use authenticated API tooling to retrieve the
schema. Do not publish internal ports to make documentation easier to access.

## Troubleshooting

| Symptom | What to inspect |
| --- | --- |
| Compose rejects a missing variable | Populate the required `.env` variables; do not remove required-key checks. |
| Specialized call returns 401/403 | Use a key accepted by `/v1/models`; WebUI's bootstrap placeholder is not a valid key. |
| Specialized call returns 500/502 | Check Nginx auth and LiteLLM logs, then FastAPI/backend connectivity. Auth-service failure must not allow the request through. |
| Chat fails before provider invocation | Inspect Presidio availability, model/language setup and the guardrail error. Do not disable masking to make a confidential request succeed. |
| OCR rejects an image | Use an actual supported raster image <=20 MiB and `ita`, `eng`, `ita+eng` or `eng+ita`. Encode `+` in query parameters. |
| Document/audio backend fails | Check the actual backend endpoint and response contract; these retained integrations are not fully validated. |
| Registry/model download is denied | Identify the blocked host and configure permitted network access; keep TLS, checksums and signatures enabled. |

## Builds behind a TLS-inspecting proxy

The local Dockerfiles accept an optional BuildKit `proxy_ca` secret. Supply a
combined CA bundle trusted by the session; do not disable certificate checking.

```bash
docker build --secret id=proxy_ca,src=/path/to/combined-ca.pem \
  -t aifactorybox-orchestrator:dev ./orchestrator
docker build --secret id=proxy_ca,src=/path/to/combined-ca.pem \
  -t aifactorybox-presidio:dev ./presidio
```

Those commands build images but do not retag or start the Compose services.
To use the secret with Compose, create a local override outside tracked files
(the bundle path must exist on your machine):

```yaml
# /path/to/compose.proxy.yaml
services:
  orchestrator:
    build:
      secrets: [proxy_ca]
  presidio-analyzer:
    build:
      secrets: [proxy_ca]
secrets:
  proxy_ca:
    file: /path/to/combined-ca.pem
```

```bash
docker compose -f docker-compose.yml -f /path/to/compose.proxy.yaml up -d --build
```

This covers dependency installation in the local Dockerfiles. Registry pulls,
other networked build steps and runtime downloads still need their own proxy
and trust configuration. Keep the CA mounted; do not copy session certificates
into image layers. See [Security](security.md) before exposing the deployment.
