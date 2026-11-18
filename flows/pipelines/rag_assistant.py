from typing import Any, Dict, Optional
from flows.sdk import AIFactoryClient


async def rag_answer_pipeline(
    client: AIFactoryClient,
    collection: str,
    question: str,
    tenant: Optional[str] = None,
    top_k: int = 3,
    model: str = "chat-small",
) -> Dict[str, Any]:
    """Esegue retrieval + rerank filtrato per tenant e genera risposta grounded."""
    filters = {"tenant": tenant} if tenant else None
    hits = await client.search(
        collection=collection,
        query=question,
        top_k=top_k,
        rerank=True,
        filters=filters,
    )
    if not hits:
        return {
            "answer": "Nessun documento pertinente trovato nella knowledge base.",
            "sources": [],
        }

    context_blocks = []
    sources = []
    for idx, hit in enumerate(hits, start=1):
        meta = hit.get("metadata", {})
        src = meta.get("source_file") or meta.get("source") or f"doc_{idx}"
        context_blocks.append(f"[{idx}] ({src}): {hit['text']}")
        sources.append({"source": src, "score": hit.get("rerank_score", hit.get("score"))})

    system_prompt = (
        "Sei un assistente aziendale. Rispondi esclusivamente basandoti sul contesto fornito. "
        "Cita le fonti usando [1], [2], ecc. Se l'informazione non è presente nel contesto, dichiaralo chiaramente."
    )
    joined_context = "\n".join(context_blocks)
    user_prompt = f"Contesto:\n{joined_context}\n\nDomanda: {question}"
    answer = await client.chat(prompt=user_prompt, system=system_prompt, model=model)
    return {"answer": answer, "sources": sources}
