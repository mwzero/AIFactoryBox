"""Lightweight PostgreSQL-backed Scheduler Worker for AIFactoryBox Flows.

Polls `flow_schedules` in `knowledge_db` and executes due automations via the public
AIFactoryBox gateway, logging every execution to `flow_runs`.
Zero Redis / Celery required.
"""
import asyncio
import json
import logging
import os
import time
import uuid
import asyncpg
from flows.sdk import AIFactoryClient
from flows.connectors.email_imap import EmailIMAPConnector
from flows.pipelines.email_triage import email_triage_pipeline
from flows.pipelines.rag_assistant import rag_answer_pipeline
from flows.pipelines.pii_audit import pii_audit_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [flow-scheduler] %(levelname)s %(message)s")
logger = logging.getLogger("aifactorybox-scheduler")

KNOWLEDGE_DB_URL = os.getenv("KNOWLEDGE_DB_URL", "")
GATEWAY_URL = os.getenv("AIFACTORYBOX_BASE_URL", "http://nginx:80")
GATEWAY_API_KEY = os.getenv("AIFACTORYBOX_API_KEY") or os.getenv("LITELLM_MASTER_KEY", "")
POLL_INTERVAL_SECONDS = int(os.getenv("SCHEDULER_POLL_SECONDS", "30"))


async def execute_scheduled_flow(flow_type: str, config: dict) -> dict:
    client = AIFactoryClient(base_url=GATEWAY_URL, api_key=GATEWAY_API_KEY)
    collection = config.get("collection", "enterprise_docs")
    tenant = config.get("tenant")

    if flow_type.startswith("email_"):
        connector = EmailIMAPConnector(
            imap_host=config.get("imap_host") or os.getenv("IMAP_HOST"),
            smtp_host=config.get("smtp_host") or os.getenv("SMTP_HOST"),
            username=config.get("email_user") or os.getenv("EMAIL_USER"),
            password=os.getenv("EMAIL_PASSWORD", ""),
        )
        mode_map = {
            "email_contract_audit": "contract_audit",
            "email_invoice_reconcile": "invoice_reconcile",
            "email_rag_draft": "rag_draft",
        }
        return await email_triage_pipeline(
            client=client,
            connector=connector,
            mode=mode_map.get(flow_type, "rag_draft"),
            collection=collection,
            tenant=tenant,
            notify_to=config.get("notify_to"),
            limit=int(config.get("limit", 3)),
            mark_seen=bool(config.get("mark_seen", False)),
        )

    if flow_type == "rag_digest":
        return await rag_answer_pipeline(
            client=client,
            collection=collection,
            question=config.get("question", "Genera un riepilogo esecutivo dei documenti recenti."),
            tenant=tenant,
        )

    if flow_type == "pii_audit":
        return await pii_audit_pipeline(
            client=client,
            text=config.get("text", "Controllo periodico conformità GDPR."),
        )

    return {"status": "skipped", "reason": f"Unsupported flow_type '{flow_type}'"}


async def run_scheduler_loop() -> None:
    if not KNOWLEDGE_DB_URL:
        logger.error("KNOWLEDGE_DB_URL is not set. Exiting scheduler.")
        return

    logger.info("Starting AIFactoryBox Flow Scheduler (poll every %ss)...", POLL_INTERVAL_SECONDS)
    pool = await asyncpg.create_pool(dsn=KNOWLEDGE_DB_URL, min_size=1, max_size=4)
    try:
        while True:
            try:
                async with pool.acquire() as conn:
                    due_rows = await conn.fetch(
                        """
                        SELECT id, name, flow_type, config_json
                        FROM flow_schedules
                        WHERE enabled = TRUE
                          AND (last_run_at IS NULL OR last_run_at <= NOW() - (interval_minutes || ' minutes')::interval)
                        ORDER BY created_at ASC
                        """
                    )
                    for row in due_rows:
                        sched_id = row["id"]
                        cfg = json.loads(row["config_json"]) if isinstance(row["config_json"], str) else dict(row["config_json"] or {})
                        start = time.perf_counter()
                        run_status = "ok"
                        output_payload: dict = {}
                        try:
                            logger.info("Running schedule '%s' (%s)...", row["name"], row["flow_type"])
                            output_payload = await execute_scheduled_flow(row["flow_type"], cfg)
                        except Exception as exc:
                            run_status = "error"
                            output_payload = {"error": str(exc)}
                            logger.warning("Schedule '%s' failed: %s", row["name"], exc)

                        duration_ms = round((time.perf_counter() - start) * 1000, 1)
                        await conn.execute(
                            """
                            INSERT INTO flow_runs (id, schedule_id, schedule_name, flow_type, status, duration_ms, output_json)
                            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
                            """,
                            uuid.uuid4(),
                            sched_id,
                            row["name"],
                            row["flow_type"],
                            run_status,
                            duration_ms,
                            json.dumps(output_payload),
                        )
                        await conn.execute(
                            "UPDATE flow_schedules SET last_run_at = NOW(), last_status = $2 WHERE id = $1",
                            sched_id,
                            run_status,
                        )
            except Exception as loop_exc:
                logger.warning("Scheduler poll error (will retry): %s", loop_exc)

            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(run_scheduler_loop())
