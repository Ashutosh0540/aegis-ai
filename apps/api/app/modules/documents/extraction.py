"""
Text extraction and chunking, used by the Celery processing task.

Kept dependency-free of FastAPI/SQLAlchemy so it can be unit tested with
plain bytes in, list[str] out — no DB or storage backend required.
"""
import io

from docx import Document as DocxDocument
from pypdf import PdfReader

from app.core.config import get_settings

settings = get_settings()


class ExtractionResult:
    def __init__(self, text: str, page_count: int | None = None):
        self.text = text
        self.page_count = page_count


def extract_text(content_type: str, data: bytes) -> ExtractionResult:
    """Dispatch to the right extractor based on content type. Raises ValueError
    for unsupported types (should be unreachable given upload validation)."""
    if content_type == "application/pdf":
        return _extract_pdf(data)
    if content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return _extract_docx(data)
    if content_type in ("text/markdown", "text/plain"):
        return _extract_plain_text(data)
    raise ValueError(f"Unsupported content type for extraction: {content_type}")


def _extract_pdf(data: bytes) -> ExtractionResult:
    reader = PdfReader(io.BytesIO(data))
    pages_text = [page.extract_text() or "" for page in reader.pages]
    text = "\n\n".join(pages_text).strip()
    # NOTE: an empty result here almost always means the PDF is scanned
    # images rather than real text. The caller (Celery task) checks this
    # and marks the version `needs_ocr` instead of `completed`.
    # TODO(milestone-later): wire pytesseract / a proper OCR pipeline here
    # when scanned-document support is prioritized.
    return ExtractionResult(text=text, page_count=len(reader.pages))


def _extract_docx(data: bytes) -> ExtractionResult:
    doc = DocxDocument(io.BytesIO(data))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    text = "\n\n".join(paragraphs).strip()
    return ExtractionResult(text=text, page_count=None)


def _extract_plain_text(data: bytes) -> ExtractionResult:
    text = data.decode("utf-8", errors="replace").strip()
    return ExtractionResult(text=text, page_count=None)


def chunk_text(
    text: str,
    chunk_size: int = settings.CHUNK_SIZE_CHARS,
    overlap: int = settings.CHUNK_OVERLAP_CHARS,
) -> list[str]:
    """
    Simple sliding-window character chunker with overlap, splitting on
    paragraph/sentence boundaries where possible so chunks don't cut mid-
    sentence more than necessary.

    This is intentionally simple for Milestone 2. Milestone 3 may swap in a
    LangChain text splitter without changing the DocumentChunk schema —
    chunks are just ordered strings either way.
    """
    if not text:
        return []

    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = min(start + chunk_size, text_length)

        if end < text_length:
            boundary = text.rfind("\n\n", start, end)
            if boundary == -1 or boundary <= start:
                boundary = text.rfind(". ", start, end)
            if boundary != -1 and boundary > start:
                end = boundary + 1

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= text_length:
            break
        start = max(end - overlap, start + 1)

    return chunks
