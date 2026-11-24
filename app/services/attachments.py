"""Extract plain text from uploaded resumes / job descriptions (PDF, DOCX, TXT, MD).

Files are read in memory, never stored, and size/page-capped. Only text leaves this module.
"""

from __future__ import annotations

import io
import zipfile

MAX_BYTES = 2 * 1024 * 1024  # 2 MB per file
MAX_PAGES = 15
MAX_CHARS = 15_000
ALLOWED = (".pdf", ".docx", ".txt", ".md")


class AttachmentError(ValueError):
    """User-safe message about a rejected file."""


def extract_text(filename: str, data: bytes) -> str:
    name = (filename or "").lower()
    if not name.endswith(ALLOWED):
        raise AttachmentError(f"“{filename}”: use a PDF, Word (.docx), .txt or .md file.")
    if len(data) > MAX_BYTES:
        raise AttachmentError(f"“{filename}” is larger than 2 MB.")
    if not data:
        raise AttachmentError(f"“{filename}” is empty.")
    try:
        if name.endswith(".pdf"):
            text = _pdf(data)
        elif name.endswith(".docx"):
            text = _docx(data)
        else:
            text = data.decode("utf-8", errors="replace")
    except AttachmentError:
        raise
    except Exception as exc:  # parser errors on malformed files  # noqa: BLE001
        raise AttachmentError(f"Couldn't read “{filename}”. Try saving it as PDF or .txt.") from exc
    text = "\n".join(line.rstrip() for line in text.splitlines() if line.strip())
    if not text:
        raise AttachmentError(
            f"No text found in “{filename}” (scanned image?). Paste the text instead."
        )
    return text[:MAX_CHARS]


def _pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        raise AttachmentError(
            "That PDF is password-protected. Remove the password or paste the text."
        )
    return "\n".join((page.extract_text() or "") for page in reader.pages[:MAX_PAGES])


def _docx(data: bytes) -> str:
    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise AttachmentError("That .docx file looks damaged.")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:  # zip-bomb guard
        if sum(i.file_size for i in zf.infolist()) > 25 * MAX_BYTES:
            raise AttachmentError("That .docx file is too large once unpacked.")
    from docx import Document

    doc = Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.append(" | ".join(c.text for c in row.cells))
    return "\n".join(parts)
