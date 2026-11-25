"""Assessment records and secure document upload. All data is synthetic."""

from datetime import date, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.core.config import get_settings
from app.core.security import create_file_token
from app.models.assessment import Assessment, Document, ProcessingStatus
from app.models.user import Role
from app.services.storage_service import StorageError

PDF = b"%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


# --- Fixtures ----------------------------------------------------------------


@pytest.fixture
def coordinator(make_user):
    return make_user(Role.SNED_COORDINATOR)


@pytest.fixture
def coord_headers(login, coordinator):
    return login(coordinator)


@pytest.fixture
def make_learner(client, coord_headers):
    counter = {"n": 0}

    def _make(**overrides):
        counter["n"] += 1
        payload = {
            "learner_code": f"AS-{counter['n']}",
            "first_name": "Sample",
            "last_name": f"Learner {counter['n']}",
            "birth_date": "2016-06-15",
            "sex": "male",
            "grade_level": "3",
            "section": "Rosal",
            "school_year": "2025-2026",
            **overrides,
        }
        response = client.post("/api/learners", headers=coord_headers, json=payload)
        assert response.status_code == 201, response.text
        return response.json()

    return _make


@pytest.fixture
def make_assessment(client, coord_headers):
    def _make(learner_id, headers=None, **overrides):
        payload = {
            "learner_id": learner_id,
            "assessment_type": "informal",
            "assessment_date": "2025-08-01",
            "assessor": "Section Adviser",
            **overrides,
        }
        response = client.post("/api/assessments", headers=headers or coord_headers, json=payload)
        assert response.status_code == 201, response.text
        return response.json()

    return _make


def upload(client, headers, assessment_id, content=PDF, filename="report.pdf", mime="application/pdf"):
    return client.post(
        f"/api/assessments/{assessment_id}/document",
        headers=headers,
        files={"file": (filename, content, mime)},
    )


def stored_files(storage):
    return [p for p in storage.root.rglob("*") if p.is_file()] if storage.root.exists() else []


# --- Assessment records ------------------------------------------------------


def test_create_and_read_assessment(client, coord_headers, coordinator, make_learner, storage):
    learner = make_learner()
    response = client.post(
        "/api/assessments",
        headers=coord_headers,
        json={
            "learner_id": learner["id"],
            "assessment_type": "formal",
            "assessment_date": "2025-09-10",
            "assessor": "  Dr. Sample Psychologist ",
            "notes": "  ",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["processing_status"] == "draft"
    assert body["assessor"] == "Dr. Sample Psychologist"
    assert body["notes"] is None
    assert body["document"] is None
    assert body["created_by_name"] == coordinator.name

    fetched = client.get(f"/api/assessments/{body['id']}", headers=coord_headers)
    assert fetched.status_code == 200
    listing = client.get("/api/assessments", headers=coord_headers, params={"learner_id": learner["id"]})
    assert listing.json()["total"] == 1


def test_assessment_validation(client, coord_headers, make_learner):
    learner = make_learner()
    response = client.post("/api/assessments", headers=coord_headers, json={"learner_id": learner["id"]})
    assert response.status_code == 422
    fields = {d["field"] for d in response.json()["error"]["details"]}
    assert {"assessment_type", "assessment_date", "assessor"} <= fields

    future = client.post(
        "/api/assessments",
        headers=coord_headers,
        json={
            "learner_id": learner["id"],
            "assessment_type": "formal",
            "assessment_date": str(date.today() + timedelta(days=1)),
            "assessor": "X",
        },
    )
    assert future.status_code == 422


# --- File checks -------------------------------------------------------------


@pytest.mark.parametrize(
    ("content", "filename", "mime"),
    [
        (b"just some text", "notes.txt", "text/plain"),
        (b"MZ\x90\x00 executable", "report.pdf", "application/pdf"),  # renamed .exe
        (b"GIF89a" + b"\x00" * 20, "scan.gif", "image/gif"),
        (PNG, "scan.pdf", "application/pdf"),  # real PNG named .pdf
    ],
)
def test_unsupported_files_are_rejected(
    client, coord_headers, make_learner, make_assessment, storage, content, filename, mime
):
    assessment = make_assessment(make_learner()["id"])
    response = upload(client, coord_headers, assessment["id"], content, filename, mime)
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_file_type"
    assert stored_files(storage) == []


def test_oversized_and_empty_files_are_rejected(
    client, coord_headers, make_learner, make_assessment, storage, monkeypatch
):
    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)
    assessment = make_assessment(make_learner()["id"])

    too_big = PDF + b"0" * (1024 * 1024)
    response = upload(client, coord_headers, assessment["id"], too_big)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"
    assert "1 MB" in response.json()["error"]["message"]

    empty = upload(client, coord_headers, assessment["id"], b"")
    assert empty.status_code == 422
    assert empty.json()["error"]["code"] == "empty_file"
    assert stored_files(storage) == []


@pytest.mark.parametrize(
    ("content", "filename", "mime"),
    [(PDF, "Report Card.PDF", "application/pdf"), (PNG, "scan.png", "image/png"), (JPG, "photo.jpeg", "image/jpeg")],
)
def test_supported_files_upload(
    client, coord_headers, make_learner, make_assessment, storage, db_session, content, filename, mime
):
    assessment = make_assessment(make_learner()["id"])
    # The client-sent MIME type is ignored; the stored type comes from the file header.
    response = upload(client, coord_headers, assessment["id"], content, filename, "application/octet-stream")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["processing_status"] == "uploaded"
    assert body["document"]["original_filename"] == filename
    assert body["document"]["mime_type"] == mime
    assert body["document"]["file_size"] == len(content)
    assert "storage_key" not in body["document"] and "checksum" not in body["document"]

    document = db_session.scalar(select(Document))
    assert document.storage_key.startswith("assessments/")
    assert filename not in document.storage_key  # random key, not the user's file name
    assert len(document.checksum) == 64
    assert [p.read_bytes() for p in stored_files(storage)] == [content]


def test_duplicate_detection_is_per_learner(client, coord_headers, make_learner, make_assessment, storage):
    learner = make_learner()
    first = make_assessment(learner["id"])
    second = make_assessment(learner["id"], assessment_date="2025-09-01")
    assert upload(client, coord_headers, first["id"]).status_code == 200

    duplicate = upload(client, coord_headers, second["id"], filename="renamed-copy.pdf")
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "duplicate_document"
    assert "2025-08-01" in duplicate.json()["error"]["message"]

    other = make_assessment(make_learner()["id"])
    assert upload(client, coord_headers, other["id"]).status_code == 200


def test_second_upload_requires_removing_the_first(client, coord_headers, make_learner, make_assessment, storage):
    assessment = make_assessment(make_learner()["id"])
    assert upload(client, coord_headers, assessment["id"]).status_code == 200
    again = upload(client, coord_headers, assessment["id"], PNG, "other.png", "image/png")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "document_exists"


# --- Access control ----------------------------------------------------------


def test_unassigned_teacher_cannot_touch_learner_assessments(
    client, make_user, login, coord_headers, make_learner, make_assessment, storage
):
    teacher = make_user(Role.TEACHER)
    headers = login(teacher)
    learner = make_learner()
    assessment = make_assessment(learner["id"])
    upload(client, coord_headers, assessment["id"])

    create = client.post(
        "/api/assessments",
        headers=headers,
        json={"learner_id": learner["id"], "assessment_type": "informal", "assessment_date": "2025-08-01", "assessor": "X"},
    )
    assert create.status_code == 404
    assert client.get("/api/assessments", headers=headers, params={"learner_id": learner["id"]}).status_code == 404
    assert client.get(f"/api/assessments/{assessment['id']}", headers=headers).status_code == 404
    assert client.get(f"/api/assessments/{assessment['id']}/document", headers=headers).status_code == 404
    assert upload(client, headers, assessment["id"], PNG, "x.png", "image/png").status_code == 404


def test_assigned_teacher_can_create_and_upload_but_not_delete(
    client, make_user, login, coord_headers, make_learner, make_assessment, storage
):
    teacher = make_user(Role.TEACHER)
    headers = login(teacher)
    learner = make_learner()
    client.post(f"/api/learners/{learner['id']}/assignments", headers=coord_headers, json={"user_id": teacher.id})

    assessment = make_assessment(learner["id"], headers=headers)
    assert assessment["created_by_name"] == teacher.name
    uploaded = upload(client, headers, assessment["id"])
    assert uploaded.status_code == 200
    assert uploaded.json()["document"]["uploaded_by_name"] == teacher.name

    delete = client.delete(f"/api/assessments/{assessment['id']}/document", headers=headers)
    assert delete.status_code == 403


def test_school_head_is_read_only(client, make_user, login, coord_headers, make_learner, make_assessment, storage):
    headers = login(make_user(Role.SCHOOL_HEAD))
    learner = make_learner()
    assessment = make_assessment(learner["id"])
    upload(client, coord_headers, assessment["id"])

    assert client.get(f"/api/assessments/{assessment['id']}", headers=headers).status_code == 200
    assert client.get(f"/api/assessments/{assessment['id']}/document", headers=headers).status_code == 200
    create = client.post(
        "/api/assessments",
        headers=headers,
        json={"learner_id": learner["id"], "assessment_type": "informal", "assessment_date": "2025-08-01", "assessor": "X"},
    )
    assert create.status_code == 403
    assert upload(client, headers, assessment["id"], PNG, "x.png", "image/png").status_code == 403


def test_assessment_endpoints_require_authentication(client, storage):
    assert client.get("/api/assessments", params={"learner_id": 1}).status_code == 401
    assert client.get("/api/assessments/1/document").status_code == 401


# --- Secure retrieval --------------------------------------------------------


def test_document_only_reachable_through_signed_url(
    client, coord_headers, make_learner, make_assessment, storage
):
    assessment = make_assessment(make_learner()["id"])
    upload(client, coord_headers, assessment["id"], filename="Report Card.pdf")

    preview = client.get(f"/api/assessments/{assessment['id']}/document", headers=coord_headers)
    assert preview.status_code == 200
    body = preview.json()
    assert body["expires_in"] == get_settings().signed_url_ttl_seconds
    assert "assessments/" not in body["url"]  # the storage key is not exposed

    served = client.get(body["url"].removeprefix("http://testserver"))
    assert served.status_code == 200
    assert served.content == PDF
    assert served.headers["content-type"] == "application/pdf"
    assert served.headers["content-disposition"].startswith("inline")
    assert served.headers["x-content-type-options"] == "nosniff"
    assert "no-store" in served.headers["cache-control"]

    download = client.get(
        f"/api/assessments/{assessment['id']}/document", headers=coord_headers, params={"download": True}
    ).json()
    served = client.get(download["url"].removeprefix("http://testserver"))
    assert served.headers["content-disposition"] == "attachment; filename*=UTF-8''Report%20Card.pdf"


def test_expired_forged_or_access_tokens_are_rejected(client, coord_headers, make_learner, make_assessment, storage, db_session):
    assessment = make_assessment(make_learner()["id"])
    upload(client, coord_headers, assessment["id"])
    key = db_session.scalar(select(Document.storage_key))

    expired = create_file_token(key, "application/pdf", "r.pdf", False, expires_in=-5)
    response = client.get(f"/api/files/{expired}")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "token_expired"

    assert client.get("/api/files/not-a-token").status_code == 401

    access_token = coord_headers["Authorization"].removeprefix("Bearer ")
    assert client.get(f"/api/files/{access_token}").status_code == 401


def test_file_token_cannot_be_used_to_sign_in(client, storage):
    token = create_file_token("assessments/x.pdf", "application/pdf", "x.pdf", False, 60)
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


# --- Delete ------------------------------------------------------------------


def test_coordinator_can_remove_document(client, coord_headers, make_learner, make_assessment, storage, db_session):
    assessment = make_assessment(make_learner()["id"])
    upload(client, coord_headers, assessment["id"])
    assert len(stored_files(storage)) == 1

    response = client.delete(f"/api/assessments/{assessment['id']}/document", headers=coord_headers)
    assert response.status_code == 200
    assert response.json()["processing_status"] == "draft"
    assert response.json()["document"] is None
    assert stored_files(storage) == []
    assert db_session.scalar(select(func.count(Document.id))) == 0

    # The same file can be uploaded again afterwards.
    assert upload(client, coord_headers, assessment["id"]).status_code == 200


def test_finalized_document_cannot_be_removed(client, coord_headers, make_learner, make_assessment, storage, db_session):
    assessment = make_assessment(make_learner()["id"])
    upload(client, coord_headers, assessment["id"])
    row = db_session.get(Assessment, assessment["id"])
    row.processing_status = ProcessingStatus.FINALIZED.value
    db_session.commit()

    response = client.delete(f"/api/assessments/{assessment['id']}/document", headers=coord_headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "assessment_finalized"
    assert len(stored_files(storage)) == 1


# --- Storage / database consistency ------------------------------------------


def test_storage_save_failure_leaves_no_row(client, coord_headers, make_learner, make_assessment, storage, monkeypatch, db_session):
    assessment = make_assessment(make_learner()["id"])

    def fail(*args, **kwargs):
        raise StorageError("boom")

    monkeypatch.setattr(storage, "save", fail)
    response = upload(client, coord_headers, assessment["id"])
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "storage_unavailable"
    assert db_session.scalar(select(func.count(Document.id))) == 0
    assert db_session.get(Assessment, assessment["id"]).processing_status == "draft"


def test_db_commit_failure_removes_stored_file(client, coord_headers, make_learner, make_assessment, storage, monkeypatch, db_session):
    assessment = make_assessment(make_learner()["id"])

    def failing_commit():
        raise OperationalError("COMMIT", {}, Exception("db down"))

    monkeypatch.setattr(db_session, "commit", failing_commit)
    with pytest.raises(OperationalError):
        upload(client, coord_headers, assessment["id"])
    monkeypatch.undo()

    assert stored_files(storage) == []
    assert db_session.scalar(select(func.count(Document.id))) == 0


def test_storage_delete_failure_keeps_row(client, coord_headers, make_learner, make_assessment, storage, monkeypatch, db_session):
    assessment = make_assessment(make_learner()["id"])
    upload(client, coord_headers, assessment["id"])

    def fail(*args, **kwargs):
        raise StorageError("boom")

    monkeypatch.setattr(storage, "delete", fail)
    response = client.delete(f"/api/assessments/{assessment['id']}/document", headers=coord_headers)
    assert response.status_code == 502
    db_session.expire_all()
    assert db_session.scalar(select(func.count(Document.id))) == 1
    assert db_session.get(Assessment, assessment["id"]).processing_status == "uploaded"
    assert len(stored_files(storage)) == 1


# --- Learner summary ---------------------------------------------------------


def test_learner_summary_counts_assessments(client, coord_headers, make_learner, make_assessment, storage):
    learner = make_learner()
    summary = client.get(f"/api/learners/{learner['id']}/summary", headers=coord_headers).json()
    assert summary["modules"]["assessments"] == {
        "available": True, "count": 0, "latest_status": None, "latest_at": None
    }

    assessment = make_assessment(learner["id"])
    upload(client, coord_headers, assessment["id"])
    module = client.get(f"/api/learners/{learner['id']}/summary", headers=coord_headers).json()["modules"]["assessments"]
    assert module["available"] is True
    assert module["count"] == 1
    assert module["latest_status"] == "uploaded"


# --- Status flow -------------------------------------------------------------


def set_status(client, headers, assessment_id, status):
    return client.patch(f"/api/assessments/{assessment_id}/status", headers=headers, json={"status": status})


def force_status(db_session, assessment_id, status):
    """Test setup only: put an assessment straight into a status (as the OCR worker would)."""
    row = db_session.get(Assessment, assessment_id)
    row.processing_status = status
    db_session.commit()


def test_manual_status_flow_and_reopen(client, coord_headers, make_learner, make_assessment, storage, db_session):
    assessment = make_assessment(make_learner()["id"])
    assert assessment["processing_status"] == "draft"
    assert assessment["next_statuses"] == []

    uploaded = upload(client, coord_headers, assessment["id"]).json()
    assert uploaded["processing_status"] == "uploaded"
    # Processing is started with POST /process, not by a manual status change.
    assert uploaded["next_statuses"] == []

    force_status(db_session, assessment["id"], "processed")
    expected_next = {
        "needs_review": ["finalized"],
        "finalized": ["needs_review"],
    }
    for target in ["needs_review", "finalized", "needs_review", "finalized"]:
        response = set_status(client, coord_headers, assessment["id"], target)
        assert response.status_code == 200, response.text
        assert response.json()["processing_status"] == target
        assert response.json()["next_statuses"] == expected_next[target]


@pytest.mark.parametrize(
    ("start", "target"),
    [
        ("draft", "finalized"),
        ("draft", "processing"),
        ("uploaded", "processing"),  # use POST /process instead
        ("uploaded", "finalized"),
        ("uploaded", "draft"),  # system-only
        ("uploaded", "uploaded"),
        ("processing", "processed"),  # set by the OCR worker only
        ("processing", "needs_review"),
        ("processing", "uploaded"),
        ("processing", "finalized"),
        ("needs_review", "processing"),  # reprocess goes through POST /process
        ("finalized", "processed"),
    ],
)
def test_invalid_status_transitions_rejected(client, coord_headers, make_learner, make_assessment, storage, db_session, start, target):
    assessment = make_assessment(make_learner()["id"])
    if start != "draft":
        upload(client, coord_headers, assessment["id"])
        force_status(db_session, assessment["id"], start)

    response = set_status(client, coord_headers, assessment["id"], target)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_status_transition"
    after = client.get(f"/api/assessments/{assessment['id']}", headers=coord_headers).json()["processing_status"]
    assert after == start


def test_unknown_status_value_rejected(client, coord_headers, make_learner, make_assessment, storage):
    assessment = make_assessment(make_learner()["id"])
    assert set_status(client, coord_headers, assessment["id"], "archived").status_code == 422


def test_only_coordinator_changes_status(client, make_user, login, coord_headers, make_learner, make_assessment, storage, db_session):
    learner = make_learner()
    assessment = make_assessment(learner["id"])
    upload(client, coord_headers, assessment["id"])
    force_status(db_session, assessment["id"], "processed")

    teacher = make_user(Role.TEACHER)
    client.post(f"/api/learners/{learner['id']}/assignments", headers=coord_headers, json={"user_id": teacher.id})
    for headers in (login(teacher), login(make_user(Role.SCHOOL_HEAD)), login(make_user(Role.SYSTEM_ADMIN))):
        assert set_status(client, headers, assessment["id"], "finalized").status_code == 403
    assert client.patch(f"/api/assessments/{assessment['id']}/status", json={"status": "finalized"}).status_code == 401
    assert set_status(client, coord_headers, 999999, "finalized").status_code == 404


def test_document_cannot_be_removed_while_processing(client, coord_headers, make_learner, make_assessment, storage, db_session):
    assessment = make_assessment(make_learner()["id"])
    upload(client, coord_headers, assessment["id"])
    force_status(db_session, assessment["id"], "processing")

    response = client.delete(f"/api/assessments/{assessment['id']}/document", headers=coord_headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "assessment_processing"
    assert len(stored_files(storage)) == 1


def test_removing_document_from_needs_review_returns_to_draft(client, coord_headers, make_learner, make_assessment, storage, db_session):
    assessment = make_assessment(make_learner()["id"])
    upload(client, coord_headers, assessment["id"])
    force_status(db_session, assessment["id"], "needs_review")

    response = client.delete(f"/api/assessments/{assessment['id']}/document", headers=coord_headers)
    assert response.status_code == 200
    assert response.json()["processing_status"] == "draft"
    assert stored_files(storage) == []


def test_transition_detects_concurrent_change(db_session, coordinator, make_learner, make_assessment, storage):
    from app.core.errors import APIError
    from app.services.assessment_status import transition

    assessment = db_session.get(Assessment, make_assessment(make_learner()["id"])["id"])
    assert assessment.processing_status == "draft"
    # Someone else moves it on behind our back.
    db_session.execute(
        Assessment.__table__.update()
        .where(Assessment.__table__.c.id == assessment.id)
        .values(processing_status="uploaded")
    )

    with pytest.raises(APIError) as exc:
        transition(db_session, assessment, ProcessingStatus.UPLOADED, manual=False)
    assert exc.value.code == "status_changed"
