"""Signed-URL file serving for the local-disk storage backend.

The token itself is the permission: it is minted only after the assessment
route has checked access, and it expires after SIGNED_URL_TTL_SECONDS. With
Supabase storage, signed URLs point at Supabase and this route returns 404.
"""

from urllib.parse import quote

from fastapi import APIRouter, Depends, Response

from app.core.errors import not_authenticated, not_found
from app.core.security import TokenError, decode_file_token
from app.services.storage_service import LocalDiskStorage, StorageBackend, StorageError, get_storage

router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("/{token}")
def serve_file(token: str, storage: StorageBackend = Depends(get_storage)) -> Response:
    if not isinstance(storage, LocalDiskStorage):
        raise not_found()
    try:
        claims = decode_file_token(token)
    except TokenError as exc:
        message = (
            "This link has expired. Open the document again from GABAY."
            if exc.code == "token_expired"
            else "This link is invalid."
        )
        raise not_authenticated(exc.code, message) from exc
    try:
        data = storage.get(claims["key"])
    except StorageError as exc:
        raise not_found("The document was not found.") from exc

    filename = claims.get("fn") or "document"
    disposition = "attachment" if claims.get("dl") else "inline"
    return Response(
        content=data,
        media_type=claims.get("ct") or "application/octet-stream",
        headers={
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(filename)}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
