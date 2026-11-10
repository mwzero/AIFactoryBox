# Privacy and access control

## Chat data before an external model call

The configured `pii-before-model` guardrail uses Presidio with `mode: pre_call`
and `default_on: true`. For supported chat message text, the intended path is:

```text
Client / Open WebUI → LiteLLM → Presidio analyzer → Presidio anonymizer
                          ↑                         │
                          └──── masked text ────────┘
                          ↓
                    Model provider → response to client
```

LiteLLM forwards the masked message after the pre-call guardrail completes.
The configured entity actions are `PERSON`, `EMAIL_ADDRESS`, `PHONE_NUMBER`,
`CREDIT_CARD` and `IBAN_CODE`, all `MASK`. The default analyzer language is
Italian; Italian and English small spaCy models are installed. English model
installation does not enable automatic language detection.

Explicit MASK actions enable the pinned native hook's failure handling for
HTTP errors and malformed response bodies. Network failures also block the
call. However, upstream can skip invalid individual recognizer entries and
PII detection can miss entities. There is no guarantee that every sensitive
value is removed. Do not disable guardrails on client keys to work around errors.

The configuration does not automatically restore original PII in the model's
answer (`output_parse_pii: false`). Images, attachments, tool arguments, arbitrary
JSON and other API types are not covered merely because a chat guardrail is
configured. Presidio is not content moderation or prompt-injection protection;
there is no Llama Guard service in this stack.

The standalone `/v1/privacy/anonymize` API is independent. It explicitly invokes
Presidio through FastAPI; chat protection does not require clients to call it.
It does not automatically protect the other specialized APIs.

## Community pass-through boundary

All published API paths reach LiteLLM, but the pinned LiteLLM Community release
requires Enterprise for native pass-through `auth: true`. The configured
specialized pass-through routes therefore use `auth: false` **inside the private
network**. Nginx validates their bearer key through an internal LiteLLM
`/v1/models` subrequest before forwarding the operation.

Missing or rejected keys are blocked. An unavailable authentication service must
fail closed at ingress. The internal authentication locations cannot be invoked
as public routes. Compose publishes only Nginx port 80; exposing LiteLLM or
FastAPI directly would bypass this specialized-key check.

Any key accepted by `/v1/models` can invoke the specialized APIs. This is not
per-endpoint authorization, model-style token budgeting or per-user pass-through
accounting. Model-key restrictions do not imply equivalent specialized-route
restrictions. Pass-through guardrails are opt-in and are not configured here.
The client bearer header is not forwarded to FastAPI by the pass-through.

## Credentials, logs and deployment

- Store real credentials in local `.env` or a deployment secret store, never tracked files.
- Use a random `LITELLM_MASTER_KEY` for administration and generated virtual keys for WebUI/clients.
- Configure model access, limits, budgets and retention explicitly. Merely running PostgreSQL does not establish an auditing or data-retention policy.
- Treat key-generation output and request/response logs as sensitive. Do not enable verbose body logging with real confidential data.
- Nginx currently listens on HTTP port 80. Add an HTTPS termination layer before sending bearer credentials over an untrusted network.
- Keep registry signatures, checksums and TLS verification enabled. Configure trusted CAs separately for builds and runtime downloads.

The Vercel adapter imports FastAPI directly and does not inherit Compose's
authentication or PII boundary. Do not treat that deployment as the protected gateway.

## Evidence and remaining validation

The tests exercise the real LiteLLM guardrail with simulated Presidio services,
including masking and rejection on tested analyzer/anonymizer failures. Ingress
key checks, multipart forwarding and error handling have also been tested.
These checks do not establish real Italian NER accuracy or provider-side privacy.

Before confidential use, verify the real analyzer/anonymizer and a controlled
provider with representative synthetic data, including streaming, any tools or
attachments you intend to support, and failure cases. Full-stack validation
remains outstanding; see [Development](development.md#validation-status).
