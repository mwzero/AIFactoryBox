"""CLI runner leggero per eseguire i flussi Python sopra AIFactoryBox."""
import argparse
import asyncio
import json
from pathlib import Path
from flows.sdk import AIFactoryClient
from flows.pipelines.ingest_safe import safe_ingest_pipeline
from flows.pipelines.rag_assistant import rag_answer_pipeline
from flows.pipelines.voice_support import voice_rag_pipeline
from flows.pipelines.pii_audit import pii_audit_pipeline
from flows.pipelines.meeting_minutes import meeting_minutes_pipeline
from flows.pipelines.contract_audit import contract_audit_pipeline
from flows.pipelines.invoice_reconcile import invoice_reconcile_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AIFactoryBox Python Flow Runner")
    parser.add_argument("--base-url", default=None, help="Gateway URL (default: $AIFACTORYBOX_BASE_URL o http://localhost)")
    parser.add_argument("--api-key", default=None, help="LiteLLM bearer key (default: $AIFACTORYBOX_API_KEY)")

    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest-safe", help="Estrae, anonimizza PII e indicizza un file")
    p_ingest.add_argument("--file", required=True, type=Path, help="Percorso del file (PDF, DOCX, TXT, PNG, JPG)")
    p_ingest.add_argument("--collection", required=True, help="Nome della collection pgvector")
    p_ingest.add_argument("--tenant", default="default", help="Identificativo tenant nei metadati")
    p_ingest.add_argument("--language", default="it", help="Lingua per OCR/Presidio (default: it)")

    p_ask = sub.add_parser("ask", help="Interroga la Knowledge Base con RAG + Rerank")
    p_ask.add_argument("--collection", required=True, help="Nome della collection pgvector")
    p_ask.add_argument("--question", required=True, help="Domanda in linguaggio naturale")
    p_ask.add_argument("--tenant", default=None, help="Filtro tenant opzionale")
    p_ask.add_argument("--top-k", type=int, default=3, help="Numero massimo di chunk nel contesto")

    p_voice = sub.add_parser("voice-ask", help="Flusso vocale: trascrizione -> RAG -> TTS")
    p_voice.add_argument("--audio", required=True, type=Path, help="File audio domanda")
    p_voice.add_argument("--collection", required=True, help="Nome della collection pgvector")
    p_voice.add_argument("--tenant", default=None, help="Filtro tenant opzionale")

    p_pii = sub.add_parser("pii-report", help="Scansiona un file o testo e genera un report di rischio GDPR")
    p_pii.add_argument("--file", type=Path, default=None, help="File da analizzare (PDF, DOCX, TXT, PNG, JPG)")
    p_pii.add_argument("--text", default=None, help="Testo grezzo da analizzare")
    p_pii.add_argument("--language", default="it", help="Lingua Presidio/OCR (default: it)")

    p_meet = sub.add_parser("meeting-minutes", help="Trascrive audio riunione, anonimizza PII ed estrae verbale")
    p_meet.add_argument("--audio", required=True, type=Path, help="File audio della riunione")
    p_meet.add_argument("--collection", default=None, help="Collection pgvector opzionale in cui archiviare il verbale")
    p_meet.add_argument("--tenant", default="default", help="Identificativo tenant")
    p_meet.add_argument("--language", default="it", help="Lingua audio/Presidio (default: it)")

    p_contract = sub.add_parser("contract-audit", help="Killer App: verifica conformità contratto contro playbook su pgvector")
    p_contract.add_argument("--file", required=True, type=Path, help="Contratto fornitore (PDF, DOCX, TXT, scansione)")
    p_contract.add_argument("--collection", required=True, help="Collection pgvector contenente le policy aziendali")
    p_contract.add_argument("--tenant", default=None, help="Filtro tenant per le policy")
    p_contract.add_argument("--language", default="it", help="Lingua OCR/Presidio (default: it)")

    p_invoice = sub.add_parser("invoice-reconcile", help="Killer App: riconcilia fattura/ricevuta contro contratti su pgvector")
    p_invoice.add_argument("--file", required=True, type=Path, help="Fattura o scontrino (PDF, immagine, TXT)")
    p_invoice.add_argument("--collection", required=True, help="Collection pgvector con contratti/ordini approvati")
    p_invoice.add_argument("--tenant", default=None, help="Filtro tenant")
    p_invoice.add_argument("--language", default="it", help="Lingua OCR/Presidio (default: it)")
    p_invoice.add_argument("--archive", action="store_true", help="Salva il report di riconciliazione nella collection")

    return parser


async def run_cli(args: argparse.Namespace) -> None:
    client = AIFactoryClient(base_url=args.base_url, api_key=args.api_key)
    if args.command == "ingest-safe":
        res = await safe_ingest_pipeline(
            client=client,
            file_path=args.file,
            collection=args.collection,
            tenant=args.tenant,
            language=args.language,
        )
    elif args.command == "ask":
        res = await rag_answer_pipeline(
            client=client,
            collection=args.collection,
            question=args.question,
            tenant=args.tenant,
            top_k=args.top_k,
        )
    elif args.command == "voice-ask":
        res = await voice_rag_pipeline(
            client=client,
            audio_path=args.audio,
            collection=args.collection,
            tenant=args.tenant,
        )
    elif args.command == "pii-report":
        res = await pii_audit_pipeline(
            client=client,
            text=args.text,
            file_path=args.file,
            language=args.language,
        )
    elif args.command == "meeting-minutes":
        res = await meeting_minutes_pipeline(
            client=client,
            audio_path=args.audio,
            collection=args.collection,
            tenant=args.tenant,
            language=args.language,
        )
    elif args.command == "contract-audit":
        res = await contract_audit_pipeline(
            client=client,
            collection=args.collection,
            file_path=args.file,
            tenant=args.tenant,
            language=args.language,
        )
    elif args.command == "invoice-reconcile":
        res = await invoice_reconcile_pipeline(
            client=client,
            collection=args.collection,
            file_path=args.file,
            tenant=args.tenant,
            language=args.language,
            archive_result=args.archive,
        )
    else:
        raise ValueError(f"Unknown command: {args.command}")

    print(json.dumps(res, indent=2, ensure_ascii=False))


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(run_cli(args))


if __name__ == "__main__":
    main()
