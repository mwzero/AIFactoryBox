from pathlib import Path
from typing import Any, Dict, Optional
from flows.sdk import AIFactoryClient

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"}
PLAIN_TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json"}


async def safe_ingest_pipeline(
    client: AIFactoryClient,
    file_path: Path,
    collection: str,
    tenant: str,
    language: str = "it",
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Estrae il testo (OCR o Docling), anonimizza i PII e indicizza su pgvector."""
    suffix = file_path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        ocr_lang = "ita+eng" if language == "it" else "eng"
        raw_text = await client.ocr(file_path, language=ocr_lang)
    elif suffix in PLAIN_TEXT_EXTENSIONS:
        raw_text = file_path.read_text(encoding="utf-8", errors="replace")
    else:
        raw_text = await client.to_markdown(file_path)

    clean_text = await client.anonymize(raw_text, language=language)

    metadata: Dict[str, Any] = {
        "source_file": file_path.name,
        "tenant": tenant,
        "sanitized": True,
    }
    if extra_metadata:
        metadata.update(extra_metadata)

    return await client.ingest(collection=collection, text=clean_text, metadata=metadata)
