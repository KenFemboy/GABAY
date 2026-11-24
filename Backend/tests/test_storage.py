"""Storage backends: Supabase REST calls (mocked) and local-disk key safety."""

import json

import httpx
import pytest

from app.services.storage_service import LocalDiskStorage, StorageError, SupabaseStorage

BASE = "https://project.supabase.co"
KEY = "service-role-key"


def make_supabase(handler):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return SupabaseStorage(BASE, KEY, "gabay-documents", client=client)


def test_supabase_save_sends_private_upload():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["url"] = str(request.url)
        seen["headers"] = request.headers
        seen["body"] = request.content
        return httpx.Response(200, json={"Key": "gabay-documents/assessments/a.pdf"})

    make_supabase(handler).save("assessments/a.pdf", b"%PDF-data", "application/pdf")
    assert seen["method"] == "POST"
    assert seen["url"] == f"{BASE}/storage/v1/object/gabay-documents/assessments/a.pdf"
    assert seen["headers"]["apikey"] == KEY
    assert seen["headers"]["authorization"] == f"Bearer {KEY}"
    assert seen["headers"]["content-type"] == "application/pdf"
    assert seen["headers"]["x-upsert"] == "false"
    assert seen["body"] == b"%PDF-data"


def test_supabase_get_and_delete():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, str(request.url), request.content))
        if request.method == "GET":
            return httpx.Response(200, content=b"bytes")
        return httpx.Response(200, json=[])

    storage = make_supabase(handler)
    assert storage.get("assessments/a.pdf") == b"bytes"
    storage.delete("assessments/a.pdf")

    assert calls[0][:2] == ("GET", f"{BASE}/storage/v1/object/gabay-documents/assessments/a.pdf")
    method, url, body = calls[1]
    assert (method, url) == ("DELETE", f"{BASE}/storage/v1/object/gabay-documents")
    assert json.loads(body) == {"prefixes": ["assessments/a.pdf"]}


def test_supabase_signed_url_for_preview_and_download():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == f"{BASE}/storage/v1/object/sign/gabay-documents/assessments/a.pdf"
        assert json.loads(request.content) == {"expiresIn": 60}
        return httpx.Response(
            200, json={"signedURL": "/object/sign/gabay-documents/assessments/a.pdf?token=abc"}
        )

    storage = make_supabase(handler)
    preview = storage.signed_url(
        "assessments/a.pdf", expires_in=60, content_type="application/pdf", filename="Report Card.pdf", download=False
    )
    assert preview == f"{BASE}/storage/v1/object/sign/gabay-documents/assessments/a.pdf?token=abc"

    download = storage.signed_url(
        "assessments/a.pdf", expires_in=60, content_type="application/pdf", filename="Report Card.pdf", download=True
    )
    assert download.endswith("?token=abc&download=Report%20Card.pdf")


@pytest.mark.parametrize("status", [400, 401, 403, 409, 500, 503])
def test_supabase_errors_raise_storage_error(status):
    storage = make_supabase(lambda request: httpx.Response(status, json={"message": "nope"}))
    with pytest.raises(StorageError):
        storage.save("assessments/a.pdf", b"x", "application/pdf")
    with pytest.raises(StorageError):
        storage.signed_url("assessments/a.pdf", expires_in=60, content_type="x", filename="a", download=False)


def test_supabase_delete_of_missing_object_is_ok():
    make_supabase(lambda request: httpx.Response(404, json={})).delete("assessments/gone.pdf")


def test_supabase_network_error_raises_storage_error():
    def handler(request):
        raise httpx.ConnectError("unreachable", request=request)

    with pytest.raises(StorageError):
        make_supabase(handler).save("assessments/a.pdf", b"x", "application/pdf")


@pytest.mark.parametrize("key", ["../secret.txt", "/etc/passwd", "assessments/../../x", "a\\b", ""])
def test_local_storage_rejects_unsafe_keys(tmp_path, key):
    storage = LocalDiskStorage(tmp_path, "http://testserver")
    with pytest.raises(StorageError):
        storage.save(key, b"x", "application/pdf")


def test_local_storage_never_overwrites(tmp_path):
    storage = LocalDiskStorage(tmp_path, "http://testserver")
    storage.save("assessments/a.pdf", b"one", "application/pdf")
    with pytest.raises(StorageError):
        storage.save("assessments/a.pdf", b"two", "application/pdf")
    assert storage.get("assessments/a.pdf") == b"one"
    storage.delete("assessments/a.pdf")
    storage.delete("assessments/a.pdf")  # missing is fine
