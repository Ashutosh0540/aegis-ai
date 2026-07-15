import io

import pytest
from docx import Document as DocxDocument

from app.modules.documents.extraction import chunk_text, extract_text


def _make_docx_bytes(paragraphs: list[str]) -> bytes:
    doc = DocxDocument()
    for p in paragraphs:
        doc.add_paragraph(p)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_extract_plain_text():
    result = extract_text("text/plain", b"Hello world.\nSecond line.")
    assert "Hello world." in result.text
    assert result.page_count is None


def test_extract_markdown_treated_as_plain_text():
    result = extract_text("text/markdown", b"# Heading\n\nSome **bold** content.")
    assert "Heading" in result.text


def test_extract_docx():
    data = _make_docx_bytes(["First paragraph.", "Second paragraph."])
    result = extract_text(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document", data
    )
    assert "First paragraph." in result.text
    assert "Second paragraph." in result.text


def test_extract_unsupported_content_type_raises():
    with pytest.raises(ValueError):
        extract_text("image/png", b"binary-ish-data")


def test_chunk_text_short_text_returns_single_chunk():
    chunks = chunk_text("Short text.", chunk_size=1000, overlap=100)
    assert chunks == ["Short text."]


def test_chunk_text_empty_returns_no_chunks():
    assert chunk_text("") == []


def test_chunk_text_splits_long_text_with_overlap():
    paragraph = "Sentence number {}. " * 1
    text = "\n\n".join(f"Paragraph {i}. " + ("word " * 50) for i in range(20))
    chunks = chunk_text(text, chunk_size=300, overlap=50)
    assert len(chunks) > 1
    # Every chunk should be non-empty and within a reasonable bound of chunk_size.
    for chunk in chunks:
        assert chunk.strip()
        assert len(chunk) <= 300 + 50  # allow some slack for boundary snapping
