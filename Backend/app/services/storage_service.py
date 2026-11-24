"""Private object storage for uploaded documents.

One interface (save, get, delete, signed_url) with two implementations:

* ``LocalDiskStorage`` – development and tests; no cloud keys needed. Signed
  URLs point at ``GET /api/files/{token}`` on this API.
* ``SupabaseStorage`` – a private Supabase Storage bucket, called from the
  backend only with the service-role key.

Never store file bytes in PostgreSQL and never hand out public bucket URLs.
"""

import logging
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Protocol
from urllib.parse import quote

import httpx

from app.core.config import Settings, get_settings
from app.core.security import create_file_token

logger = logging.getLogger(__name__)


class StorageError(Exception):
    """The storage provider failed or is unreachable."""


class StorageBackend(Protocol):
    def save(self, key: str, data: bytes, content_type: str) -> None: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None:
        """Remove the object. A missing object counts as success."""

    def signed_url(
        self, key: str, *, expires_in: int, content_type: str, filename: str, download: bool
    ) -> str: ...


def validate_key(key: str) -> str:
    path = PurePosixPath(key)
    if not key or path.is_absolute() or ".." in path.parts or "\\" in key:
        raise StorageError(f"Invalid storage key: {key!r}")
    return key


class LocalDiskStorage:
    def __init__(self, root: str | Path, public_api_url: str) -> None:
        self.root = Path(root).resolve()
        self.public_api_url = public_api_url.rstrip("/")

    def _path(self, key: str) -> Path:
        path = (self.root / validate_key(key)).resolve()
        if self.root not in path.parents:
            raise StorageError(f"Invalid storage key: {key!r}")
        return path

    def save(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as fh:  # never overwrite an existing object
                fh.write(data)
        except OSError as exc:
            raise StorageError(f"Could not save {key}") from exc

    def get(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except OSError as exc:
            raise StorageError(f"Could not read {key}") from exc

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError(f"Could not delete {key}") from exc

    def signed_url(
        self, key: str, *, expires_in: int, content_type: str, filename: str, download: bool
    ) -> str:
        validate_key(key)
        token = create_file_token(key, content_type, filename, download, expires_in)
        return f"{self.public_api_url}/api/files/{token}"


class SupabaseStorage:
    """Supabase Storage REST API (https://supabase.com/docs/reference/api)."""

    def __init__(
        self,
        url: str,
        service_role_key: str,
        bucket: str,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = url.rstrip("/")
        self.bucket = bucket
        self.client = client or httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0))
        self.headers = {"apikey": service_role_key, "Authorization": f"Bearer {service_role_key}"}

    def _object_url(self, *parts: str) -> str:
        return f"{self.base_url}/storage/v1/object/" + "/".join(parts)

    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        headers = {**self.headers, **kwargs.pop("headers", {})}
        try:
            response = self.client.request(method, url, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise StorageError(f"Supabase Storage request failed: {exc.__class__.__name__}") from exc
        return response

    @staticmethod
    def _raise_for(response: httpx.Response, action: str) -> None:
        if response.is_success:
            return
        # Body may include the bucket/key; log it server-side only.
        logger.warning("Supabase Storage %s failed: %s %s", action, response.status_code, response.text[:500])
        raise StorageError(f"Supabase Storage {action} failed with HTTP {response.status_code}")

    def save(self, key: str, data: bytes, content_type: str) -> None:
        url = self._object_url(self.bucket, quote(validate_key(key), safe="/"))
        response = self._request(
            "POST", url, content=data, headers={"Content-Type": content_type, "x-upsert": "false"}
        )
        self._raise_for(response, "upload")

    def get(self, key: str) -> bytes:
        url = self._object_url(self.bucket, quote(validate_key(key), safe="/"))
        response = self._request("GET", url)
        self._raise_for(response, "download")
        return response.content

    def delete(self, key: str) -> None:
        url = self._object_url(self.bucket)
        response = self._request("DELETE", url, json={"prefixes": [validate_key(key)]})
        if response.status_code == 404:
            return
        self._raise_for(response, "delete")

    def signed_url(
        self, key: str, *, expires_in: int, content_type: str, filename: str, download: bool
    ) -> str:
        url = self._object_url("sign", self.bucket, quote(validate_key(key), safe="/"))
        response = self._request("POST", url, json={"expiresIn": expires_in})
        self._raise_for(response, "sign")
        try:
            body = response.json()
            path = body.get("signedURL") or body["signedUrl"]
        except (ValueError, KeyError, AttributeError) as exc:
            raise StorageError("Supabase Storage returned an unexpected sign response") from exc
        signed = f"{self.base_url}/storage/v1{path}"
        if download:
            separator = "&" if "?" in signed else "?"
            signed += f"{separator}download={quote(filename)}"
        return signed


def build_storage(settings: Settings) -> StorageBackend:
    if settings.storage_backend == "supabase":
        return SupabaseStorage(
            settings.supabase_url, settings.supabase_service_role_key, settings.supabase_bucket
        )
    return LocalDiskStorage(settings.storage_local_dir, settings.public_api_url)


@lru_cache
def _default_storage() -> StorageBackend:
    return build_storage(get_settings())


def get_storage() -> StorageBackend:
    """FastAPI dependency; tests override it."""
    return _default_storage()
