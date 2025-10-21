# apps/extractor_service/ingest/msg_parse.py
from __future__ import annotations

import os
import mimetypes
import tempfile
from pathlib import Path
from typing import List, Tuple, Optional, Union, Iterable

try:
    import extract_msg  # .msg (Outlook) parser
except Exception as e:  # pragma: no cover
    extract_msg = None
    _IMPORT_ERROR = e


Attachment = Tuple[str, bytes, str]  # (filename, data, mimetype)


def _first_bytes(b: bytes, n: int = 8) -> bytes:
    return b[:n] if isinstance(b, (bytes, bytearray)) else bytes(b)[:n]


def _sniff_image_kind(b: bytes) -> Optional[str]:
    sig = _first_bytes(b, 12)
    if sig.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image"
    if sig.startswith(b"\xFF\xD8\xFF"):
        return "image"
    if sig.startswith(b"II*\x00") or sig.startswith(b"MM\x00*"):
        return "image"
    if sig.startswith(b"GIF87a") or sig.startswith(b"GIF89a"):
        return "image"
    if sig.startswith(b"RIFF") and sig[8:12] == b"WEBP":
        return "image"
    return None


def guess_kind(payload: Union[bytes, str, dict], filename: Optional[str] = None) -> str:
    """
    Minimal heuristic used by the worker to route payloads.

    Returns one of: "email", "image", "pdf", "document".
    """
    # 1) Filename-based
    if filename:
        ext = Path(filename).suffix.lower()
        if ext in {".eml", ".msg"}:
            return "email"
        if ext == ".pdf":
            return "pdf"
        if ext in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".gif", ".webp", ".bmp"}:
            return "image"

    # 2) Content-based (cheap, no external deps)
    if isinstance(payload, (bytes, bytearray)):
        head = _first_bytes(payload, 12)
        if head.startswith(b"%PDF-"):
            return "pdf"
        img = _sniff_image_kind(payload)
        if img:
            return img

    # Default
    return "document"


def parse_msg(raw: bytes) -> Tuple[str, List[Attachment]]:
    """
    Parse a raw Outlook .msg file (bytes) and return:
      - body (str)
      - attachments: list of (filename, data, mimetype)
    """
    if extract_msg is None:
        raise ImportError(
            "extract_msg is not available in this environment"
        ) from _IMPORT_ERROR

    # Use a named temp file because extract_msg expects a file path
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".msg") as tmp:
            tmp.write(raw)
            tmp.flush()
            tmp_path = tmp.name

        msg = extract_msg.Message(tmp_path)
        body = msg.body or msg.htmlBody or ""  # body fallback

        attachments: List[Attachment] = []
        for a in getattr(msg, "attachments", []) or []:
            # data
            data = getattr(a, "data", None)
            if data is None:
                # Some versions expose .data as a property that must be read
                # via ._data or .attachData; be defensive:
                data = getattr(a, "_data", None) or getattr(a, "attachData", None)
            if data is None:
                continue

            # name
            name_candidates: Iterable[Optional[str]] = (
                getattr(a, "longFilename", None),
                getattr(a, "shortFilename", None),
                getattr(a, "filename", None),
            )
            name = next((n for n in name_candidates if n), "attachment")

            # mime
            mime = mimetypes.guess_type(name)[0] or "application/octet-stream"

            attachments.append((name, data, mime))

        return body, attachments
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


__all__ = ["parse_msg", "guess_kind", "Attachment"]
