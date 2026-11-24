"""Turn a module's declared fields (+ optional file attachments) into one labelled input."""

from __future__ import annotations

from starlette.datastructures import FormData, UploadFile

from app.services.attachments import AttachmentError, extract_text
from app.services.modules_registry import ModuleSpec


class InputError(ValueError):
    """User-safe validation message."""


async def compose_input(spec: ModuleSpec, form: FormData) -> tuple[str, list[str]]:
    """Return (combined text, notes for the user). Raises InputError on bad input."""
    if not spec.fields:
        value = form.get("user_input")
        return (value if isinstance(value, str) else ""), []
    parts: list[str] = []
    notes: list[str] = []
    for f in spec.fields:
        raw = form.get(f.name)
        text = raw.strip() if isinstance(raw, str) else ""
        if f.kind == "select" and f.options and text not in f.options:
            text = f.options[0]
        upload = form.get(f"{f.name}_file") if f.upload else None
        if isinstance(upload, UploadFile) and upload.filename:
            data = await upload.read(3 * 1024 * 1024)
            try:
                extracted = extract_text(upload.filename, data)
            except AttachmentError as exc:
                raise InputError(str(exc)) from exc
            notes.append(
                f"Read “{upload.filename}” for {f.label.lower()} ({len(extracted):,} characters)."
            )
            text = f"{text}\n\n{extracted}".strip() if text else extracted
        if f.required and not text:
            raise InputError(f"Please add {f.label.lower()}: paste it or attach a file.")
        if text:
            parts.append(f"{f.name.replace('_', ' ').upper()}:\n{text}")
    return "\n\n".join(parts), notes
