"""CLI runner leggero per eseguire i flussi Python sopra AIFactoryBox."""
import argparse
import asyncio
import json
from pathlib import Path
from flows.sdk import AIFactoryClient
from flows.pipelines.ingest_safe import safe_ingest_pipeline
from flows.pipelines.rag_assistant import rag_answer_pipeline
from flows.pipelines.voice_support import voice_rag_pipeline


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
    else:
        raise ValueError(f"Unknown command: {args.command}")

    print(json.dumps(res, indent=2, ensure_ascii=False))


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(run_cli(args))


if __name__ == "__main__":
    main()
