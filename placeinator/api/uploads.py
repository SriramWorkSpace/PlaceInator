"""Shared upload-size guard for the multipart file endpoints (resumes, JDs).

Every route that accepts an ``UploadFile`` previously read it in full via
``await file.read()`` with no cap -- an oversized or malformed file could
exhaust memory or trigger pathological parse time in pdfplumber before any
format/content validation ever ran. This bounds it: reading aborts the
moment the limit is exceeded, so an oversized upload never gets fully
buffered into memory in the first place.
"""

from __future__ import annotations

from fastapi import HTTPException, UploadFile, status

# Generous for a heavily scanned, image-only multi-page PDF resume or JD --
# the largest legitimate case this app handles -- while still bounding
# memory. Plain-text/DOCX/PDF resumes and JDs are typically well under 1 MB.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

_CHUNK_BYTES = 1024 * 1024


async def read_upload(file: UploadFile) -> bytes:
    """Reads an uploaded file's bytes in chunks, raising 413 the moment the
    total exceeds MAX_UPLOAD_BYTES rather than buffering an arbitrarily
    large upload into memory first."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                f"file exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit",
            )
        chunks.append(chunk)
    return b"".join(chunks)
