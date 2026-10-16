# Security, Privacy & Compliance

AIFactoryBox is built with a "Zero-Trust Data Boundary" principle for enterprise LLM consumption.

## PII Masking Pipeline (Microsoft Presidio)

Before any unstructured prompt leaves the corporate boundary to public LLMs (e.g. OpenAI, Anthropic), the Presidio Analyzer scans and masks entities:

1. **Detection**: Recognizes `PERSON`, `EMAIL_ADDRESS`, `PHONE_NUMBER`, `IBAN`, `CREDIT_CARD`, and custom regex patterns.
2. **Replacement**: Replaces identified tokens with deterministic placeholders (e.g., `<PERSON_1>`, `<EMAIL_1>`).
3. **De-anonymization (Optional)**: Maps back tokens upon response reception inside the private perimeter.

## Prompt Injection & Content Guardrails (Llama Guard 3)

The `/v1/security/guardrail` primitive evaluates incoming prompts and model responses against safety taxonomy guidelines:
- Prompt injection and jailbreak attempts (e.g., DAN, system role overriding).
- Harmful content categories and policy violations.
- System prompt and secret exfiltration attempts.

## Access Control & Auditing

- **LiteLLM Master Key**: Restricts administrative actions and key issuance.
- **Tenant API Keys**: Allows scoping rate-limits and token budgets per department or team.
- **PostgreSQL Audit Log**: Stores request metadata, latency, token consumption, and status codes for compliance audits.
