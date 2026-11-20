from pathlib import Path
from typing import Any, Dict, Optional
from flows.sdk import AIFactoryClient


async def meeting_minutes_pipeline(
    client: AIFactoryClient,
    audio_path: Path,
    collection: Optional[str] = None,
    tenant: str = "default",
    language: str = "it",
    model: str = "chat-small",
) -> Dict[str, Any]:
    """Trascrive una riunione, maschera i PII, estrae decisioni/action item e opzionalmente indicizza su pgvector."""
    transcript = await client.transcribe(audio_path, language=language)
    sanitized_transcript = await client.anonymize(transcript, language=language)

    system_prompt = (
        "Sei un assistente executive. Trasforma la trascrizione anonimizzata della riunione in un verbale "
        "strutturato in Markdown con le seguenti sezioni: "
        "1) Sintesi Esecutiva, 2) Decisioni Prese, 3) Action Item (con responsabile e scadenza se citati)."
    )
    minutes_md = await client.chat(
        prompt=f"Trascrizione riunione:\n{sanitized_transcript}",
        system=system_prompt,
        model=model,
    )

    ingest_result = None
    if collection:
        ingest_result = await client.ingest(
            collection=collection,
            text=f"# Verbale: {audio_path.name}\n\n{minutes_md}\n\n## Trascrizione\n{sanitized_transcript}",
            metadata={
                "source_file": audio_path.name,
                "tenant": tenant,
                "doc_type": "meeting_minutes",
                "sanitized": True,
            },
        )

    return {
        "source_file": audio_path.name,
        "sanitized_transcript": sanitized_transcript,
        "minutes_markdown": minutes_md,
        "indexed": ingest_result,
    }
