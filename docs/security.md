# Privacy and access control

LiteLLM runs `pii-before-model` as a default pre-call Presidio guardrail.
The default analyzer language is Italian, with Italian and English small spaCy
models installed. Explicit MASK entity actions enable the pinned native hook's fail-closed
handling of HTTP errors and malformed response bodies. Invalid individual
recognizer entries may still be skipped by the upstream hook.
Network failures block the call too. Do not disable this guardrail on client keys.

Masking applies to text supported by LiteLLM's native Presidio hook, including
chat message text. This is not a guarantee of redaction of images, files,
tool arguments, every API type or every personal datum. Validate detection on
representative data before sending confidential material externally. No automatic
de-anonymization is enabled. Masked tokens remain masked in model responses.
The `/v1/privacy/anonymize` endpoint is independent; calling it is not necessary
for the chat guardrail to run. It is also not automatically applied to other
specialized APIs.

All published APIs are routed through LiteLLM. Community pass-through routes
use `auth: false` internally because their native authentication requires
Enterprise in the pinned release. Nginx protects specialized routes using an
internal authentication subrequest to LiteLLM `/v1/models`; missing or rejected
keys cannot reach the pass-through. Neither LiteLLM nor FastAPI publishes a host
port in Compose. Do not expose those internal ports or bypass Nginx.

The ingress check validates a key, not fine-grained access to specialized APIs.
It does not provide model-style token budgeting or per-user accounting for
pass-through operations. Any key accepted by `/v1/models` can use them. Do not
assume chat guardrails inspect specialized payloads or multipart uploads.

Set a random master key and URL-safe database password in `.env`; these are no
longer embedded in Compose/YAML. Give Open WebUI a generated LiteLLM virtual key,
not the administrative master key. Configure budgets/limits per virtual key as
needed; merely running PostgreSQL does not establish an auditing policy.

Presidio is PII detection, not content moderation or prompt-injection protection.
No Llama Guard service is deployed or advertised.
