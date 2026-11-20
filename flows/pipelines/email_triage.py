"""Enterprise Email/PEC Triage Pipeline: IMAP -> Killer App (Contract/Invoice/RAG) -> Draft/Notify."""
from typing import Any, Dict, Optional
from flows.sdk import AIFactoryClient
from flows.connectors.email_imap import EmailIMAPConnector
from flows.pipelines.contract_audit import contract_audit_pipeline
from flows.pipelines.invoice_reconcile import invoice_reconcile_pipeline
from flows.pipelines.rag_assistant import rag_answer_pipeline


async def email_triage_pipeline(
    client: AIFactoryClient,
    connector: EmailIMAPConnector,
    mode: str = "rag_draft",
    collection: str = "enterprise_docs",
    tenant: Optional[str] = None,
    notify_to: Optional[str] = None,
    limit: int = 3,
    mark_seen: bool = False,
) -> Dict[str, Any]:
    """Legge le email non lette, esegue la pipeline AI scelta e salva bozze o invia report."""
    emails = connector.fetch_unread_emails(limit=limit, mark_seen=mark_seen)
    processed = []

    for mail in emails:
        if mode == "contract_audit":
            target_file = mail.attachments[0] if mail.attachments else None
            res = await contract_audit_pipeline(
                client=client,
                collection=collection,
                file_path=target_file,
                contract_text=None if target_file else mail.body_text,
                tenant=tenant,
            )
            report_text = res["audit_report"]
        elif mode == "invoice_reconcile":
            target_file = mail.attachments[0] if mail.attachments else None
            res = await invoice_reconcile_pipeline(
                client=client,
                collection=collection,
                file_path=target_file,
                invoice_text=None if target_file else mail.body_text,
                tenant=tenant,
            )
            report_text = res["reconciliation_report"]
        else:
            res = await rag_answer_pipeline(
                client=client,
                collection=collection,
                question=f"{mail.subject}\n{mail.body_text}",
                tenant=tenant,
            )
            report_text = res["answer"]

        action_taken = "logged_only"
        if notify_to:
            connector.send_email(
                to_addr=notify_to,
                subject=f"[AIFactoryBox:{mode}] {mail.subject}",
                body=report_text,
            )
            action_taken = f"notified:{notify_to}"
        elif mode == "rag_draft" and mail.sender:
            connector.save_draft(
                to_addr=mail.sender,
                subject=f"Re: {mail.subject}",
                body=report_text,
            )
            action_taken = "saved_draft"

        processed.append({
            "uid": mail.uid,
            "subject": mail.subject,
            "sender": mail.sender,
            "attachments_count": len(mail.attachments),
            "action": action_taken,
            "preview": report_text[:300],
        })

    return {
        "mode": mode,
        "collection": collection,
        "emails_scanned": len(emails),
        "processed": processed,
    }
