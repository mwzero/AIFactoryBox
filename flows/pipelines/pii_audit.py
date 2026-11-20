from pathlib import Path
import re
from typing import Any, Dict, Optional, Union
from flows.sdk import AIFactoryClient
from flows.pipelines.ingest_safe import IMAGE_EXTENSIONS, PLAIN_TEXT_EXTENSIONS

PLACEHOLDER_RE = re.compile(r"<([A-Z_]+)>")


async def pii_audit_pipeline(
    client: AIFactoryClient,
    text: Optional[str] = None,
    file_path: Optional[Union[str, Path]] = None,
    language: str = "it",
) -> Dict[str, Any]:
    """Analizza un testo o documento, maschera i PII via Presidio e genera un report di rischio GDPR."""
    if not text and not file_path:
        raise ValueError("Provide either 'text' or 'file_path'.")

    source = "raw_text"
    raw_text = text or ""
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

    sanitized_text = await client.anonymize(raw_text, language=language)
    detected_tags = PLACEHOLDER_RE.findall(sanitized_text)
    counts: Dict[str, int] = {}
    for tag in detected_tags:
        counts[tag] = counts.get(tag, 0) + 1

    total = len(detected_tags)
    if total == 0:
        risk_level = "LOW"
    elif total <= 3:
        risk_level = "MEDIUM"
    else:
        risk_level = "HIGH"

    return {
        "source": source,
        "language": language,
        "gdpr_risk_level": risk_level,
        "entities_masked_total": total,
        "entities_breakdown": counts,
        "sanitized_text": sanitized_text,
    }
