"""Upload checks: extension, real file type (magic bytes), size and checksum."""

import hashlib
import re
from dataclasses import dataclass
from pathlib import PurePath
from typing import BinaryIO

from app.core.errors import APIError

CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class FileKind:
    mime_type: str
    extension: str  # canonical extension used in the storage key
    magic: bytes


PDF = FileKind("application/pdf", "pdf", b"%PDF-")
PNG = FileKind("image/png", "png", b"\x89PNG\r\n\x1a\n")
JPEG = FileKind("image/jpeg", "jpg", b"\xff\xd8\xff")

ALLOWED_EXTENSIONS: dict[str, FileKind] = {"pdf": PDF, "png": PNG, "jpg": JPEG, "jpeg": JPEG}
ALLOWED_LABEL = "PDF, JPG or PNG"


@dataclass(frozen=True)
class ValidatedFile:
    data: bytes
    kind: FileKind
    size: int
    checksum: str
    filename: str


def unsupported(message: str | None = None) -> APIError:
    return APIError(
        415, "unsupported_file_type", message or f"Only {ALLOWED_LABEL} files can be uploaded."
    )


_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def sanitize_filename(name: str | None) -> str:
    """Keep only a safe base name for display; it is never used as a path."""
    base = PurePath((name or "").replace("\\", "/")).name
    base = _CONTROL_CHARS.sub("", base).strip()
    if len(base) > 255:
        stem, dot, ext = base.rpartition(".")
        base = (stem[: 250 - len(ext)] + dot + ext) if dot else base[:255]
    return base or "document"


def detect_kind(header: bytes) -> FileKind | None:
    for kind in (PDF, PNG, JPEG):
        if header.startswith(kind.magic):
            return kind
    return None


def read_and_validate(stream: BinaryIO, filename: str | None, max_bytes: int) -> ValidatedFile:
    safe_name = sanitize_filename(filename)
    extension = safe_name.rpartition(".")[2].lower() if "." in safe_name else ""
    expected = ALLOWED_EXTENSIONS.get(extension)
    if expected is None:
        raise unsupported()

    # Read at most max_bytes + 1 so an oversized upload is never fully buffered.
    digest = hashlib.sha256()
    chunks: list[bytes] = []
    size = 0
    while chunk := stream.read(CHUNK_SIZE):
        size += len(chunk)
        if size > max_bytes:
            limit_mb = max_bytes // (1024 * 1024)
            raise APIError(413, "file_too_large", f"The file is larger than the {limit_mb} MB limit.")
        digest.update(chunk)
        chunks.append(chunk)

    if size == 0:
        raise APIError(422, "empty_file", "The file is empty.")

    data = b"".join(chunks)
    detected = detect_kind(data[:16])
    if detected is None:
        raise unsupported("The file content is not a valid PDF, JPG or PNG.")
    if detected is not expected:
        raise unsupported(
            f"The file content does not match its .{extension} extension. "
            f"Only {ALLOWED_LABEL} files can be uploaded."
        )

    return ValidatedFile(
        data=data, kind=detected, size=size, checksum=digest.hexdigest(), filename=safe_name
    )
