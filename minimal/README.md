# Minimal local gateway

A text-only AIFactoryBox variant: the standard LiteLLM Proxy forwards requests
to Ollama, which runs `gemma3:1b` locally. The stable client alias is
`chat-default`.

```text
Client → LiteLLM Proxy → Ollama → gemma3:1b
          bearer key      model weights in local storage
```

There is no custom FastAPI server, PostgreSQL, Nginx, Open WebUI or Presidio in
this variant. No cloud model provider is configured. It supports text chat,
summaries, classification and text extraction to the extent the small model
can perform them. It does **not** provide OCR, audio, dedicated embeddings,
reranking, PII masking, virtual-key management or persistent budgets.

Use synthetic data for experiments. A local model is not an anonymization
service. Downloading images/weights and installing dependencies needs network
access; inference can run locally once everything is available. Small weights
do not mean a small runtime image or eliminate RAM requirements.

All commands below start at the repository root. This directory is independent
of the full stack's `docker-compose.yml` and `.env`.

## Choose an execution mode

| Mode | LiteLLM | Ollama | Setup |
| --- | --- | --- | --- |
| Native Python | Python virtual environment | Installed on the computer | No Docker required |
| Python + Docker | Python virtual environment | Docker | Adds a loopback-only Ollama port for the host gateway |
| Docker | Docker | Docker | Two long-running containers plus a temporary model-download service |

The Python and Docker configurations use the same `config.yaml`, model and
alias. Native Python defaults to port 4000 on loopback. In full Docker mode,
only gateway port 4000 is published, also on loopback; Ollama stays internal.
Do not run both gateways on the same host port at once.

## 1. Create a local key

Python 3.11+ is required. Initialization uses only the standard library, so it
can run before installing dependencies:

```bash
python minimal/run.py --init
```

This generates a random key in ignored `minimal/.env`, with owner-only file
permissions where supported, without printing it. Repeating the command leaves
the existing file and key unchanged. Keep it private. An empty or placeholder
key is rejected by the launcher.

`minimal/.env.example` documents the supported variables:

- `LITELLM_MASTER_KEY`: the single shared client/admin key for this local gateway.
- `OLLAMA_API_BASE`: defaults to `http://127.0.0.1:11434` for Python; Docker overrides it with `http://ollama:11434`.

Shell environment variables take precedence over `minimal/.env`. The launcher
removes inherited `DATABASE_URL` and `DIRECT_URL` before launching the proxy;
there is no database in the configuration. It preserves proxy settings and
adds loopback addresses to the proxy exclusions. Do not add full-stack settings to
this variant's environment file.

## 2A. Run LiteLLM in Python

```bash
python -m venv minimal/.venv
minimal/.venv/bin/python -m pip install -r minimal/requirements.txt
```

Install Ollama using its official installation instructions at
<https://ollama.com/download>. If its desktop app or background service is
already running, do not start another server. Otherwise, in a separate terminal:

```bash
ollama serve
```

Download the model, then start the gateway:

```bash
ollama pull gemma3:1b
minimal/.venv/bin/python minimal/run.py
```

The launcher starts the standard `litellm` executable from the same Python
environment, using the minimal configuration. It does not implement another
HTTP API. To change the gateway port:

```bash
minimal/.venv/bin/python minimal/run.py --port 4001
```

On Windows, replace `minimal/.venv/bin/python` with
`minimal\.venv\Scripts\python.exe`. The Python launcher works without Bash.

### Python gateway with Ollama in Docker

Instead of installing Ollama on the computer, start only the Ollama service
with the host-access override and download the model through the temporary
client service:

```bash
docker compose -f minimal/compose.yaml -f minimal/compose.python.yaml up -d ollama
docker compose -f minimal/compose.yaml -f minimal/compose.python.yaml run --rm pull-model
minimal/.venv/bin/python minimal/run.py
```

The override publishes Ollama at `127.0.0.1:11434` for the native Python gateway.
That local Ollama endpoint has no LiteLLM authentication; do not bind it to a
public interface. Do not use this override for full Docker mode.

## 2B. Run both services in Docker

After initialization, no host Python dependency installation is needed:

```bash
docker compose -f minimal/compose.yaml up -d
```

Compose waits for the Ollama server health check, runs `pull-model` to download
`gemma3:1b`, and starts the gateway only after the pull succeeds. The download
container exits normally; Ollama and LiteLLM remain running. Weights are stored
in a named volume and reused on subsequent pulls. A successful pull does not
prove inference readiness; the first chat request loads the model and can be slow.

```bash
docker compose -f minimal/compose.yaml ps -a
docker compose -f minimal/compose.yaml logs --tail=100 pull-model gateway ollama
```

The images are pinned to Ollama `0.6.8` (supports Gemma 3) and the full gateway's
LiteLLM `1.83.14` stable release. This is a minimal deployment topology, not a
claim that the upstream images or Python proxy dependencies are tiny.

## 3. Make a functional request

`http://127.0.0.1:4000/docs` is API documentation, not a chat UI.
A public liveness check is available at:

```bash
curl --fail http://127.0.0.1:4000/health/liveliness
```

A live process is not proof that Ollama can generate text. For a real chat,
use an OpenAI-compatible client with the generated key and alias
`chat-default`. This example reads the key without printing it. It requires
the native Python dependencies installed above, even if the gateway runs in Docker:

```bash
minimal/.venv/bin/python - <<'PY'
import os
from dotenv import dotenv_values
from openai import OpenAI

settings = dotenv_values("minimal/.env")
client = OpenAI(
    base_url="http://127.0.0.1:4000/v1",
    api_key=os.environ.get("LITELLM_MASTER_KEY") or settings["LITELLM_MASTER_KEY"],
    timeout=180,
)
response = client.chat.completions.create(
    model="chat-default",
    messages=[{"role": "user", "content": "Rispondi con una breve frase in italiano."}],
    max_tokens=64,
)
print(response.choices[0].message.content)
PY
```

For a Docker-only setup without the Python client packages, use any HTTP client.
For example, in Bash, copy the generated key from the local `minimal/.env` file
and paste it at this hidden prompt (never into chat or a public issue):

```bash
read -r -s -p 'Local gateway key: ' AIFACTORYBOX_API_KEY
printf '\n'
curl --fail-with-body http://127.0.0.1:4000/v1/chat/completions \
  -H "Authorization: Bearer $AIFACTORYBOX_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"model":"chat-default","messages":[{"role":"user","content":"Ciao!"}],"max_tokens":64}'
unset AIFACTORYBOX_API_KEY
```

For SSE streaming, set `stream=True` and iterate the returned chunks. The
public alias stays `chat-default`; `gemma3:1b` is the backend model identifier.
Model quality, supported prompts and performance still require evaluation.

## Stop and retain models

Stop a native gateway with Ctrl+C. Do not stop an Ollama service that another
application is using. To stop the isolated Compose project:

```bash
docker compose -f minimal/compose.yaml down
```

The named model volume remains. Only add `--volumes` when you intentionally want
to delete this project's downloaded weights. Native Ollama stores weights in
its own managed model directory, independently of the Compose volume.

## Troubleshooting and network access

| Symptom | Check |
| --- | --- |
| Launcher refuses startup | Run `--init`, install requirements into the Python environment used to launch, and remove placeholder keys. |
| Port already in use | Stop the other gateway or choose another native port. Docker's mapping is in `compose.yaml`. |
| Chat returns a connection error | Confirm Ollama is running and `OLLAMA_API_BASE` is reachable from the gateway's execution environment. |
| Model not found | Run the model pull against the same Ollama instance the gateway calls. |
| Download/init service fails | Inspect `pull-model` and Ollama logs; verify registry/artifact access and CA trust. |
| 401/403 | Use the key from `minimal/.env`, or the overriding shell variable if one is set. No virtual keys are available. |
| A health check passes but chat fails | Health proves liveness only. Send a real chat request to test model loading and inference. |

Model downloads use the Ollama registry (`registry.ollama.ai`) and may follow
artifact redirects. Permit the destinations actually needed by the runtime;
do not disable TLS verification. Behind a TLS-inspecting proxy, the Ollama
**server** needs the trusted CA bundle because it downloads the weights. For
Docker, use a local Compose override with a read-only bundle mount and
`SSL_CERT_FILE` for Ollama, plus the supported proxy environment. The model-pull
client calls the server; it does not store a second copy of the weights.

## Development checks and validation status

Using the repository development environment (or install `pytest` alongside
these requirements in the minimal environment):

```bash
LITELLM_LOCAL_MODEL_COST_MAP=True .venv/bin/pytest minimal/tests -q
LITELLM_MASTER_KEY=sk-compose-validation-key-long-enough docker compose -f minimal/compose.yaml config --quiet
LITELLM_MASTER_KEY=sk-compose-validation-key-long-enough docker compose -f minimal/compose.yaml -f minimal/compose.python.yaml config --quiet
```

Tests exercise private/idempotent key generation, refusal of missing credentials
and a real Python LiteLLM HTTP process with an Ollama-compatible local service
double. The live test checks authentication, alias routing, chat and SSE, while
an unusable inherited database URL confirms the minimal launcher does not need
a database. These tests do not measure Gemma quality or prove real Ollama inference.

During implementation, the Ollama model registry returned HTTP 403 from the
cloud environment. Actual model download, Gemma inference and full Docker
startup therefore remain unverified here. No inference-readiness claim is made.
