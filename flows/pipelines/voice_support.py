from pathlib import Path
from typing import Any, Dict, Optional
from flows.sdk import AIFactoryClient
from flows.pipelines.rag_assistant import rag_answer_pipeline


async def voice_rag_pipeline(
    client: AIFactoryClient,
    audio_path: Path,
    collection: str,
    tenant: Optional[str] = None,
    language: str = "it",
    voice: str = "it_IT-riccardo-x_low",
) -> Dict[str, Any]:
    """Pipeline vocale end-to-end: Audio -> Trascrizione -> RAG -> Sintesi vocale."""
    transcript = await client.transcribe(audio_path, language=language)
    rag_res = await rag_answer_pipeline(
        client=client,
        collection=collection,
        question=transcript,
        tenant=tenant,
    )
    tts_output = await client.synthesize(text=rag_res["answer"], voice=voice)
    return {
        "transcript": transcript,
        "answer": rag_res["answer"],
        "sources": rag_res["sources"],
        "audio": tts_output,
    }
