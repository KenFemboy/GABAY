"""Stage 5 OCR: pipeline, job queue/worker and review API. All data is synthetic.

Tesseract is replaced by a fake engine except in the one smoke test that
runs only when Tesseract is installed.
"""

import io
import shutil
from datetime import UTC, datetime, timedelta

import pytest
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.models.assessment import Assessment
from app.models.ocr import OcrJob, OcrPage, OcrPageSource, OcrPageStatus
from app.models.user import Role
from app.services import ocr_job_service
from app.services.ocr_service import (
    PAGE_LIMIT_MESSAGE,
    OcrError,
    build_text_and_confidence,
    extract_pages,
    preprocess,
)
from app.workers.ocr_worker import process_one

# --- Synthetic documents -----------------------------------------------------


def text_pdf(pages: list[str]) -> bytes:
    """Minimal valid PDF with one Helvetica text line per page (a real text layer)."""
    body = [b"<< /Type /Catalog /Pages 2 0 R >>"]
    kids = b" ".join(b"%d 0 R" % (4 + 2 * i) for i in range(len(pages)))
    body.append(b"<< /Type /Pages /Kids [" + kids + b"] /Count %d >>" % len(pages))
    body.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for i, text in enumerate(pages):
        stream = b"BT /F1 12 Tf 72 720 Td (" + text.encode() + b") Tj ET"
        body.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % (5 + 2 * i)
        )
        body.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    out = b"%PDF-1.4\n"
    offsets = []
    for number, obj in enumerate(body, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(body) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer << /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(body) + 1, xref)
    return out


def blank_image(color: int = 255, size=(400, 300)) -> Image.Image:
    return Image.new("RGB", size, (color, color, color))


def scanned_pdf(n_pages: int) -> bytes:
    """Image-only PDF (no text layer), like a scanner produces."""
    images = [blank_image(255 - i) for i in range(n_pages)]
    buf = io.BytesIO()
    images[0].save(buf, format="PDF", save_all=True, append_images=images[1:], resolution=100)
    return buf.getvalue()


def png_bytes() -> bytes:
    buf = io.BytesIO()
    blank_image().save(buf, format="PNG")
    return buf.getvalue()


class FakeEngine:
    """Returns scripted results per call; an Exception instance is raised instead."""

    def __init__(self, results=None, default=("recognised text", 92.0)):
        self.results = list(results or [])
        self.default = default
        self.calls = 0
        self.images = []

    def recognize(self, image):
        self.calls += 1
        self.images.append(image)
        result = self.results.pop(0) if self.results else self.default
        if isinstance(result, Exception):
            raise result
        return result


# --- Pipeline ----------------------------------------------------------------


def test_text_layer_pdf_skips_ocr():
    engine = FakeEngine()
    pages = extract_pages(
        text_pdf(["Informal assessment of reading skills", "Second page with plenty of text"]),
        "application/pdf",
        engine=engine,
    )
    assert engine.calls == 0
    assert [p.page_number for p in pages] == [1, 2]
    assert all(p.source == OcrPageSource.TEXT_LAYER and p.status == OcrPageStatus.OK for p in pages)
    assert pages[0].text == "Informal assessment of reading skills"
    assert pages[0].confidence is None


def test_short_text_layer_falls_back_to_ocr():
    engine = FakeEngine()
    pages = extract_pages(text_pdf(["x"]), "application/pdf", engine=engine)
    assert engine.calls == 1
    assert pages[0].source == OcrPageSource.OCR


def test_scanned_pdf_and_png_are_ocrd():
    engine = FakeEngine()
    pages = extract_pages(scanned_pdf(2), "application/pdf", engine=engine)
    assert engine.calls == 2
    assert [(p.page_number, p.source, p.text, p.confidence) for p in pages] == [
        (1, OcrPageSource.OCR, "recognised text", 92.0),
        (2, OcrPageSource.OCR, "recognised text", 92.0),
    ]
    assert all(img.mode == "L" for img in engine.images)

    pages = extract_pages(png_bytes(), "image/png", engine=FakeEngine())
    assert len(pages) == 1 and pages[0].status == OcrPageStatus.OK


def test_one_bad_page_does_not_fail_the_document():
    engine = FakeEngine(results=[("one", 90.0), RuntimeError("boom"), ("three", 85.0)])
    pages = extract_pages(scanned_pdf(3), "application/pdf", engine=engine)
    assert [p.page_number for p in pages] == [1, 2, 3]
    assert [p.status for p in pages] == [OcrPageStatus.OK, OcrPageStatus.FAILED, OcrPageStatus.OK]
    assert pages[0].text == "one" and pages[2].text == "three"
    assert "boom" not in (pages[1].error or "")  # no raw exception text leaks


def test_page_limit(monkeypatch):
    settings = get_settings().model_copy(update={"ocr_max_pages": 2})
    pages = extract_pages(scanned_pdf(3), "application/pdf", engine=FakeEngine(), settings=settings)
    assert [p.status for p in pages] == [OcrPageStatus.OK, OcrPageStatus.OK, OcrPageStatus.FAILED]
    assert pages[2].error == PAGE_LIMIT_MESSAGE


def test_corrupt_files_raise_ocr_error():
    with pytest.raises(OcrError) as exc:
        extract_pages(b"%PDF-1.4 garbage", "application/pdf", engine=FakeEngine())
    assert exc.value.code == "pdf_unreadable"
    with pytest.raises(OcrError):
        extract_pages(b"\x89PNG\r\n\x1a\nnot really", "image/png", engine=FakeEngine())


def test_preprocess_grayscale_and_resizes():
    small = preprocess(blank_image(size=(400, 300)))
    assert small.mode == "L" and max(small.size) == 2500
    big = preprocess(blank_image(size=(5000, 4000)))
    assert max(big.size) == 3500
    assert big.size[0] / big.size[1] == pytest.approx(5000 / 4000, rel=0.01)


def test_build_text_keeps_lines_and_weights_confidence():
    data = {
        "text": ["", "Hello", "world", "Next", "", "Para"],
        "conf": [-1, 90, 80, 50, -1, 100],
        "block_num": [1, 1, 1, 1, 1, 2],
        "par_num": [1, 1, 1, 1, 1, 1],
        "line_num": [0, 1, 1, 2, 2, 1],
    }
    text, conf = build_text_and_confidence(data)
    assert text == "Hello world\nNext\n\nPara"
    # (90*5 + 80*5 + 50*4 + 100*4) / 18
    assert conf == pytest.approx(80.6, abs=0.05)
    assert build_text_and_confidence({"text": []}) == ("", None)


def _tesseract_available() -> bool:
    settings = get_settings()
    return bool(settings.tesseract_cmd or shutil.which("tesseract"))


@pytest.mark.skipif(not _tesseract_available(), reason="Tesseract is not installed")
def test_real_tesseract_reads_rendered_text():
    from app.services.ocr_service import TesseractEngine

    img = Image.new("RGB", (1200, 300), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 96)
    except OSError:
        font = ImageFont.load_default(size=96)
    draw.text((40, 90), "GABAY 2025", fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    settings = get_settings().model_copy(update={"ocr_languages": "eng"})
    pages = extract_pages(buf.getvalue(), "image/png", engine=TesseractEngine(settings), settings=settings)
    assert "GABAY" in pages[0].text.upper()
    assert pages[0].confidence and pages[0].confidence > 50


# --- Job queue, worker and API -----------------------------------------------


@pytest.fixture
def coordinator(make_user):
    return make_user(Role.SNED_COORDINATOR)


@pytest.fixture
def coord_headers(login, coordinator):
    return login(coordinator)


@pytest.fixture
def uploaded(client, coord_headers, storage):
    """Factory: learner + assessment + uploaded document. Returns (learner, assessment)."""
    counter = {"n": 0}

    def _make(content=None, filename="report.pdf", mime="application/pdf"):
        counter["n"] += 1
        learner = client.post(
            "/api/learners",
            headers=coord_headers,
            json={
                "learner_code": f"OCR-{counter['n']}",
                "first_name": "Sample",
                "last_name": f"Learner {counter['n']}",
                "birth_date": "2016-06-15",
                "sex": "female",
                "grade_level": "3",
                "section": "Rosal",
                "school_year": "2025-2026",
            },
        ).json()
        assessment = client.post(
            "/api/assessments",
            headers=coord_headers,
            json={
                "learner_id": learner["id"],
                "assessment_type": "formal",
                "assessment_date": "2025-08-01",
                "assessor": "Psychologist",
            },
        ).json()
        response = client.post(
            f"/api/assessments/{assessment['id']}/document",
            headers=coord_headers,
            files={"file": (filename, content or scanned_pdf(2), mime)},
        )
        assert response.status_code == 200, response.text
        return learner, response.json()

    return _make


@pytest.fixture
def run_worker(db_session, storage):
    factory = sessionmaker(bind=db_session.get_bind(), autoflush=False)

    def _run(engine=None):
        worked = process_one(factory, storage, engine or FakeEngine())
        # The API client shares db_session across requests; the worker wrote
        # through its own session, so drop any cached (now stale) rows.
        db_session.expire_all()
        return worked

    return _run


def process(client, headers, assessment_id):
    return client.post(f"/api/assessments/{assessment_id}/process", headers=headers)


def get_ocr(client, headers, assessment_id):
    response = client.get(f"/api/assessments/{assessment_id}/ocr", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def status_of(client, headers, assessment_id):
    return client.get(f"/api/assessments/{assessment_id}", headers=headers).json()


def test_process_queues_and_returns_immediately(client, coord_headers, uploaded, db_session):
    _, assessment = uploaded()
    response = process(client, coord_headers, assessment["id"])
    assert response.status_code == 202
    assert response.json()["processing_status"] == "processing"
    job = db_session.scalar(select(OcrJob))
    assert job.status == "queued" and job.attempts == 0
    assert db_session.scalar(select(func.count(OcrPage.id))) == 0  # nothing ran yet

    again = process(client, coord_headers, assessment["id"])
    assert again.status_code == 409
    assert db_session.scalar(select(func.count(OcrJob.id))) == 1


def test_process_requires_document(client, coord_headers, storage):
    learner = client.post(
        "/api/learners",
        headers=coord_headers,
        json={"learner_code": "OCR-X", "first_name": "A", "last_name": "B", "birth_date": "2016-06-15",
              "sex": "male", "grade_level": "3", "section": "Rosal", "school_year": "2025-2026"},
    ).json()
    assessment = client.post(
        "/api/assessments",
        headers=coord_headers,
        json={"learner_id": learner["id"], "assessment_type": "informal", "assessment_date": "2025-08-01", "assessor": "X"},
    ).json()
    response = process(client, coord_headers, assessment["id"])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "no_document"


def test_worker_high_confidence_goes_to_processed(client, coord_headers, uploaded, run_worker):
    _, assessment = uploaded()
    process(client, coord_headers, assessment["id"])
    assert run_worker(FakeEngine(default=("Reads at grade 2 level", 95.0))) is True
    assert run_worker() is False  # queue empty

    assert status_of(client, coord_headers, assessment["id"])["processing_status"] == "processed"
    result = get_ocr(client, coord_headers, assessment["id"])
    assert result["job"]["status"] == "succeeded"
    assert [p["page_number"] for p in result["pages"]] == [1, 2]
    assert result["pages"][0]["raw_text"] == "Reads at grade 2 level"
    assert result["pages"][0]["reviewed_text"] is None
    assert result["summary"]["mean_confidence"] == 95.0
    assert result["summary"]["failed_pages"] == 0


def test_text_layer_pdf_goes_to_processed(client, coord_headers, uploaded, run_worker):
    _, assessment = uploaded(text_pdf(["This learner reads fluently at grade level."]))
    process(client, coord_headers, assessment["id"])
    engine = FakeEngine()
    run_worker(engine)
    assert engine.calls == 0
    assert status_of(client, coord_headers, assessment["id"])["processing_status"] == "processed"
    page = get_ocr(client, coord_headers, assessment["id"])["pages"][0]
    assert page["source"] == "text_layer" and page["confidence"] is None


@pytest.mark.parametrize(
    "results",
    [
        [("ok", 95.0), ("blurry", 40.0)],  # low confidence page
        [("ok", 95.0), RuntimeError("tesseract crashed")],  # one failed page
    ],
)
def test_worker_low_confidence_or_failed_page_needs_review(client, coord_headers, uploaded, run_worker, results):
    _, assessment = uploaded()
    process(client, coord_headers, assessment["id"])
    run_worker(FakeEngine(results=results))
    assert status_of(client, coord_headers, assessment["id"])["processing_status"] == "needs_review"
    result = get_ocr(client, coord_headers, assessment["id"])
    assert len(result["pages"]) == 2
    assert result["pages"][0]["status"] == "ok"


def test_worker_all_pages_failed_returns_to_uploaded(client, coord_headers, uploaded, run_worker):
    _, assessment = uploaded()
    process(client, coord_headers, assessment["id"])
    run_worker(FakeEngine(results=[RuntimeError("a"), RuntimeError("b")]))

    data = status_of(client, coord_headers, assessment["id"])
    assert data["processing_status"] == "uploaded"
    assert data["ocr_error"] == "No page of the document could be read."
    assert get_ocr(client, coord_headers, assessment["id"])["job"]["error_code"] == "all_pages_failed"

    # Can be retried; a successful retry clears the error.
    assert process(client, coord_headers, assessment["id"]).status_code == 202
    run_worker()
    data = status_of(client, coord_headers, assessment["id"])
    assert data["processing_status"] == "processed"
    assert data["ocr_error"] is None


def test_worker_engine_unavailable_fails_job(client, coord_headers, uploaded, run_worker):
    class MissingTesseract(FakeEngine):
        def check(self):
            raise OcrError("ocr_unavailable", "Tesseract OCR is not installed on the processing server.")

    _, assessment = uploaded()
    process(client, coord_headers, assessment["id"])
    run_worker(MissingTesseract())
    data = status_of(client, coord_headers, assessment["id"])
    assert data["processing_status"] == "uploaded"
    assert "not installed" in data["ocr_error"]


def test_worker_corrupt_pdf_fails_job(client, coord_headers, uploaded, run_worker):
    # Passes upload validation (starts with %PDF-) but pdfium cannot open it.
    _, assessment = uploaded(b"%PDF-1.4\nnot a real pdf body")
    process(client, coord_headers, assessment["id"])
    run_worker()
    assert status_of(client, coord_headers, assessment["id"])["ocr_error"].startswith("The PDF could not be opened")


def test_reprocess_replaces_pages_and_discards_edits(client, coord_headers, uploaded, run_worker):
    _, assessment = uploaded()
    aid = assessment["id"]
    process(client, coord_headers, aid)
    run_worker(FakeEngine(default=("first run", 95.0)))
    client.put(f"/api/assessments/{aid}/ocr/pages/1", headers=coord_headers, json={"reviewed_text": "edited"})

    assert process(client, coord_headers, aid).status_code == 202
    run_worker(FakeEngine(default=("second run", 96.0)))
    pages = get_ocr(client, coord_headers, aid)["pages"]
    assert [p["raw_text"] for p in pages] == ["second run", "second run"]
    assert all(p["reviewed_text"] is None for p in pages)


def test_finalized_cannot_be_reprocessed(client, coord_headers, uploaded, run_worker):
    _, assessment = uploaded()
    aid = assessment["id"]
    process(client, coord_headers, aid)
    run_worker()
    client.patch(f"/api/assessments/{aid}/status", headers=coord_headers, json={"status": "finalized"})
    response = process(client, coord_headers, aid)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "assessment_not_processable"


def test_review_edit_keeps_raw_text_and_can_revert(client, coord_headers, coordinator, uploaded, run_worker):
    _, assessment = uploaded()
    aid = assessment["id"]
    process(client, coord_headers, aid)
    run_worker(FakeEngine(default=("Teh learner reeds", 60.0)))

    response = client.put(
        f"/api/assessments/{aid}/ocr/pages/2", headers=coord_headers, json={"reviewed_text": "The learner reads"}
    )
    assert response.status_code == 200
    page = response.json()
    assert page["raw_text"] == "Teh learner reeds"
    assert page["reviewed_text"] == "The learner reads"
    assert page["reviewed_by_name"] == coordinator.name
    assert get_ocr(client, coord_headers, aid)["summary"]["reviewed_pages"] == 1

    reverted = client.put(f"/api/assessments/{aid}/ocr/pages/2", headers=coord_headers, json={"reviewed_text": None})
    assert reverted.json()["reviewed_text"] is None
    assert reverted.json()["reviewed_by_name"] is None
    assert client.put(f"/api/assessments/{aid}/ocr/pages/9", headers=coord_headers, json={"reviewed_text": "x"}).status_code == 404
    too_long = "x" * 100_001
    assert client.put(f"/api/assessments/{aid}/ocr/pages/1", headers=coord_headers, json={"reviewed_text": too_long}).status_code == 422


def test_review_edit_blocked_outside_review(client, coord_headers, uploaded, run_worker):
    _, assessment = uploaded()
    aid = assessment["id"]
    process(client, coord_headers, aid)
    # Still processing.
    response = client.put(f"/api/assessments/{aid}/ocr/pages/1", headers=coord_headers, json={"reviewed_text": "x"})
    assert response.status_code == 409
    run_worker()
    client.patch(f"/api/assessments/{aid}/status", headers=coord_headers, json={"status": "finalized"})
    response = client.put(f"/api/assessments/{aid}/ocr/pages/1", headers=coord_headers, json={"reviewed_text": "x"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "assessment_not_editable"


def test_ocr_permissions(client, make_user, login, coord_headers, uploaded, run_worker):
    learner, assessment = uploaded()
    aid = assessment["id"]
    process(client, coord_headers, aid)
    run_worker()

    head = login(make_user(Role.SCHOOL_HEAD))
    assert client.get(f"/api/assessments/{aid}/ocr", headers=head).status_code == 200
    assert client.put(f"/api/assessments/{aid}/ocr/pages/1", headers=head, json={"reviewed_text": "x"}).status_code == 403
    assert process(client, head, aid).status_code == 403

    stranger = login(make_user(Role.TEACHER))
    assert client.get(f"/api/assessments/{aid}/ocr", headers=stranger).status_code == 404
    assert client.put(f"/api/assessments/{aid}/ocr/pages/1", headers=stranger, json={"reviewed_text": "x"}).status_code == 404
    assert process(client, stranger, aid).status_code == 404

    teacher = make_user(Role.TEACHER)
    client.post(f"/api/learners/{learner['id']}/assignments", headers=coord_headers, json={"user_id": teacher.id})
    assigned = login(teacher)
    assert client.put(f"/api/assessments/{aid}/ocr/pages/1", headers=assigned, json={"reviewed_text": "ok"}).status_code == 200
    assert process(client, assigned, aid).status_code == 202

    assert client.get(f"/api/assessments/{aid}/ocr").status_code == 401


def test_stale_running_job_is_requeued_then_failed(client, coord_headers, uploaded, db_session):
    _, assessment = uploaded()
    process(client, coord_headers, assessment["id"])
    settings = get_settings().model_copy(update={"ocr_max_attempts": 2, "ocr_job_timeout_minutes": 30})

    def make_stale():
        job = ocr_job_service.claim_next(db_session)
        job.started_at = datetime.now(UTC) - timedelta(hours=1)
        db_session.commit()

    make_stale()  # attempt 1 "crashed"
    assert ocr_job_service.recover_stale(db_session, settings) == 1
    assert db_session.scalar(select(OcrJob)).status == "queued"

    make_stale()  # attempt 2 "crashed"
    ocr_job_service.recover_stale(db_session, settings)
    job = db_session.scalar(select(OcrJob))
    assert job.status == "failed" and job.error_code == "job_timeout"
    assert db_session.get(Assessment, assessment["id"]).processing_status == "uploaded"


def test_recent_running_job_is_left_alone(client, coord_headers, uploaded, db_session):
    _, assessment = uploaded()
    process(client, coord_headers, assessment["id"])
    ocr_job_service.claim_next(db_session)
    assert ocr_job_service.recover_stale(db_session) == 0
    assert db_session.scalar(select(OcrJob)).status == "running"


def test_config_status_reports_ocr(client):
    data = client.get("/api/config/status").json()
    assert isinstance(data["ocr_available"], bool)
    assert isinstance(data["ocr_languages_installed"], list)
