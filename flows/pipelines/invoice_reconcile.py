from pathlib import Path
from typing import Any, Dict, Optional, Union
from flows.sdk import AIFactoryClient
from flows.pipelines.ingest_safe import IMAGE_EXTENSIONS, PLAIN_TEXT_EXTENSIONS


async def invoice_reconcile_pipeline(
    client: AIFactoryClient,
    collection: str,
    file_path: Optional[Union[str, Path]] = None,
    invoice_text: Optional[str] = None,
    tenant: Optional[str] = None,
    language: str = "it",
    archive_result: bool = False,
    model: str = "chat-small",
) -> Dict[str, Any]:
    """Killer App 2: Riconciliazione fattura/ricevuta (OCR/Docling) contro contratti/ordini su pgvector."""
    if not file_path and not invoice_text:
        raise ValueError("Provide either 'file_path' or 'invoice_text'.")

    source = "raw_invoice"
    raw_text = invoice_text or ""
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

    # 1. Mascheramento PII prima dell'invio al modello
    sanitized_invoice = await client.anonymize(raw_text, language=language)

    # 2. Ricerca del contratto o ordine di acquisto di riferimento su pgvector
    filters = {"tenant": tenant} if tenant else None
    reference_hits = await client.search(
        collection=collection,
        query=f"contratto ordine acquisto importo corrispettivo termini pagamento {sanitized_invoice[:300]}",
        top_k=4,
        rerank=True,
        filters=filters,
    )

    ref_context = "\n".join(
        f"[DOC-{idx}] ({h.get('metadata', {}).get('source_file') or h.get('metadata', {}).get('source', 'contract')}): {h['text']}"
        for idx, h in enumerate(reference_hits, start=1)
    ) or "Nessun ordine o contratto di riferimento trovato nella Knowledge Base."

    system_prompt = (
        "Sei un controller amministrativo. Confronta i dati della fattura ricevuta con i documenti contrattuali/ordini "
        "recuperati dalla Knowledge Base.\n"
        "Restituisci:\n"
        "1. **Esito Controllo**: `APPROVATA` oppure `BLOCCATA PER DISCREPANZA`\n"
        "2. **Confronto Voci** (Importi, Termini di pagamento, Oggetto fornitura, Riferimenti [DOC-n])\n"
        "3. **Eventuali Anomalie Rilevate**."
    )
    user_prompt = (
        f"DOCUMENTI CONTRATTUALI / ORDINI DI RIFERIMENTO:\n{ref_context}\n\n"
        f"FATTURA DA RICONCILIARE:\n{sanitized_invoice[:5000]}"
    )
    reconciliation = await client.chat(prompt=user_prompt, system=system_prompt, model=model, temperature=0.1)

    archived = None
    if archive_result:
        archived = await client.ingest(
            collection=collection,
            text=f"# Riconciliazione Fattura: {source}\n\n{reconciliation}",
            metadata={
                "source_file": source,
                "tenant": tenant or "default",
                "doc_type": "invoice_reconciliation",
                "sanitized": True,
            },
        )

    return {
        "source": source,
        "collection": collection,
        "tenant": tenant,
        "references_matched": len(reference_hits),
        "reconciliation_report": reconciliation,
        "archived": archived,
    }
