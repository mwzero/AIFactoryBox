from pathlib import Path
from typing import Any, Dict, Optional, Union
from flows.sdk import AIFactoryClient
from flows.pipelines.ingest_safe import IMAGE_EXTENSIONS, PLAIN_TEXT_EXTENSIONS


async def contract_audit_pipeline(
    client: AIFactoryClient,
    collection: str,
    file_path: Optional[Union[str, Path]] = None,
    contract_text: Optional[str] = None,
    tenant: Optional[str] = None,
    language: str = "it",
    top_k: int = 5,
    model: str = "chat-small",
) -> Dict[str, Any]:
    """Killer App 1: Estrae un contratto, maschera i PII e verifica la conformità rispetto al playbook aziendale su pgvector."""
    if not file_path and not contract_text:
        raise ValueError("Provide either 'file_path' or 'contract_text'.")

    source = "raw_contract"
    raw_text = contract_text or ""
    if file_path is not None:
        path = Path(file_path)
        source = path.name
        suffix = path.suffix.lower()
        if suffix in IMAGE_EXTENSIONS:
            ocr_lang = "ita+eng" if language == "it" else "eng"
            raw_text = await client.ocr(path, language=ocr_lang)
        elif suffix in PLAIN_TEXT_EXTENSIONS:
            raw_text = path.read_text(encoding="utf-8", errors="replace")
        else:
            raw_text = await client.to_markdown(path)

    # 1. Scudo GDPR locale prima di qualsiasi chiamata al modello LLM
    sanitized_contract = await client.anonymize(raw_text, language=language)

    # 2. Retrieval delle policy/clausole standard dalla Knowledge Base aziendale
    filters = {"tenant": tenant} if tenant else None
    policy_hits = await client.search(
        collection=collection,
        query="clausole standard penali recesso pagamento responsabilita SLA foro competente",
        top_k=top_k,
        rerank=True,
        filters=filters,
    )

    policy_context = "\n".join(
        f"[POLICY-{idx}] ({h.get('metadata', {}).get('source_file') or h.get('metadata', {}).get('source', 'playbook')}): {h['text']}"
        for idx, h in enumerate(policy_hits, start=1)
    ) or "Nessuna policy specifica trovata nella collection; applica le best practice legali standard."

    system_prompt = (
        "Sei un Senior Legal & Compliance Auditor. Analizza il contratto fornitore (già anonimizzato per la privacy) "
        "confrontandolo con le policy aziendali interne fornite.\n"
        "Produci un report strutturato con:\n"
        "1. **Verdetto Sintetico** (`CONFORME`, `CONFORME CON RISERVE`, `NON CONFORME`)\n"
        "2. **Tabella Analisi Clausole** (Clausola, Stato, Riferimento Policy [POLICY-n], Rischio)\n"
        "3. **Proposta di Redlining** per le clausole critiche."
    )
    user_prompt = (
        f"POLICY AZIENDALI DI RIFERIMENTO:\n{policy_context}\n\n"
        f"TESTO CONTRATTO DA VERIFICARE (ANONIMIZZATO):\n{sanitized_contract[:6000]}"
    )
    audit_report = await client.chat(prompt=user_prompt, system=system_prompt, model=model, temperature=0.1)

    return {
        "source": source,
        "collection": collection,
        "tenant": tenant,
        "pii_masked": True,
        "policies_consulted": len(policy_hits),
        "audit_report": audit_report,
    }
