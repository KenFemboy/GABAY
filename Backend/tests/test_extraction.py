"""Stage 6: rule-based extraction, versioning, review and approval. Synthetic data only."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models.ocr import OcrPage
from app.models.user import Role
from app.scripts.make_ocr_samples import (
    FILIPINO_NOTES,
    FORMAL_REPORT_PAGES,
    HEADER,
    REPORT_PAGES,
    text_layer_pdf,
)
from app.services.extraction.rules import RuleBasedExtractor
from app.services.extraction.schema import PageText
from app.workers.ocr_worker import process_one


def pages_from(contents: list[list[str]]) -> list[PageText]:
    return [PageText(page_number=i + 1, text="\n".join(HEADER + lines)) for i, lines in enumerate(contents)]


def by_category(findings, category):
    return [f for f in findings if f.category.value == category]


# --- Rule extractor ----------------------------------------------------------


def test_informal_report_present_levels_strengths_needs_recommendations():
    findings = RuleBasedExtractor().extract(pages_from(REPORT_PAGES)).findings

    levels = {f.domain.value for f in by_category(findings, "present_level")}
    assert levels == {"reading", "mathematics", "behavior_social", "communication", "motor"}

    strengths = [f.text for f in by_category(findings, "strength")]
    needs = [f.text for f in by_category(findings, "need")]
    assert "The learner recognizes all letters of the alphabet and most letter sounds." in strengths
    assert "Can button and unbutton large buttons independently." in strengths
    assert "Has difficulty with subtraction and word problems." in needs
    assert "Copies shapes and letters slowly." in needs

    recs = [f.text for f in by_category(findings, "recommendation")]
    assert recs == [
        "Daily phonics practice using decodable texts (15 minutes).",
        "Use of manipulatives for addition and subtraction.",
        "Visual schedule and short work periods with breaks.",
        "Fine motor activities: tracing, cutting, and pegboards.",
        "Refer to the SNED Coordinator for a formal assessment.",
    ]
    # Signature lines are not findings.
    assert not any("Prepared by" in f.text or "Noted by" in f.text for f in findings)
    # The informal report has no labelled diagnosis, so none is invented.
    assert by_category(findings, "diagnosis") == []


def test_formal_report_all_categories():
    findings = RuleBasedExtractor().extract(pages_from(FORMAL_REPORT_PAGES)).findings
    assert [f.text for f in by_category(findings, "diagnosis")] == [
        "Autism Spectrum Disorder, Level 1, with language delay."
    ]
    assert len(by_category(findings, "strength")) >= 3
    assert "Reading comprehension is below grade level." in [f.text for f in by_category(findings, "need")]
    levels = {f.domain.value: f.text for f in by_category(findings, "present_level")}
    assert levels["mathematics"] == "Adds and subtracts two-digit numbers without regrouping."
    assert "inferential questions" in levels["reading"]
    assert len(by_category(findings, "recommendation")) == 5
    # "Reason for referral" mentions difficulty but is not a findings section.
    assert not any("Referred by" in f.text for f in findings)


def test_no_diagnosis_without_label():
    pages = [PageText(page_number=1, text="I. READING\nThe learner shows signs that could suggest dyslexia.")]
    findings = RuleBasedExtractor().extract(pages).findings
    assert by_category(findings, "diagnosis") == []


def test_filipino_headings_and_cues():
    findings = RuleBasedExtractor().extract(pages_from([FILIPINO_NOTES])).findings
    assert [f.text for f in by_category(findings, "recommendation")] == [
        "Dagdag na pagsasanay sa pagbasa araw-araw."
    ]
    assert any("nahihirapan" in f.text for f in by_category(findings, "need"))
    assert any("masigla" in f.text for f in by_category(findings, "strength"))


def test_source_references_point_at_the_quote():
    pages = pages_from(REPORT_PAGES + FORMAL_REPORT_PAGES)
    texts = {p.page_number: p.text for p in pages}
    findings = RuleBasedExtractor().extract(pages).findings
    assert findings
    for f in findings:
        assert f.source is not None
        span = texts[f.source.page][f.source.start:f.source.end]
        assert " ".join(span.split()) == f.source.quote


def test_ocr_blank_lines_inside_a_paragraph_are_joined():
    text = "I. READING\nComprehension is limited to recalling the\n\nmain character of the story.\n"
    findings = RuleBasedExtractor().extract([PageText(page_number=1, text=text)]).findings
    assert "Comprehension is limited to recalling the main character of the story." in [
        f.text for f in by_category(findings, "need")
    ]


def test_inline_label_inside_recommendation_does_not_start_section():
    text = "RECOMMENDATIONS\nFine motor activities: tracing, cutting, and pegboards.\nWeekly reading support.\n"
    findings = RuleBasedExtractor().extract([PageText(page_number=1, text=text)]).findings
    recs = by_category(findings, "recommendation")
    assert [f.text for f in recs][0] == "Fine motor activities: tracing, cutting, and pegboards."
    assert recs[0].domain.value == "motor"
    assert by_category(findings, "present_level") == []


# --- API flow ----------------------------------------------------------------


class NoOcr:
    """Text-layer PDFs never reach the OCR engine."""

    def recognize(self, image):  # pragma: no cover - must not be called
        raise AssertionError("OCR should not run for text-layer PDFs")


@pytest.fixture
def coordinator(make_user):
    return make_user(Role.SNED_COORDINATOR)


@pytest.fixture
def coord_headers(login, coordinator):
    return login(coordinator)


@pytest.fixture
def finalized(client, coord_headers, storage, db_session):
    """Factory: learner + finalized assessment whose text is the formal sample report."""
    factory = sessionmaker(bind=db_session.get_bind(), autoflush=False)
    counter = {"n": 0}

    def _make(contents=None, finalize=True):
        counter["n"] += 1
        learner = client.post(
            "/api/learners",
            headers=coord_headers,
            json={
                "learner_code": f"EXT-{counter['n']}", "first_name": "Sample", "last_name": f"B{counter['n']}",
                "birth_date": "2016-05-10", "sex": "male", "grade_level": "3", "section": "Rosal",
                "school_year": "2025-2026",
            },
        ).json()
        assessment = client.post(
            "/api/assessments",
            headers=coord_headers,
            json={"learner_id": learner["id"], "assessment_type": "formal", "assessment_date": "2025-07-15",
                  "assessor": "Psychologist"},
        ).json()
        aid = assessment["id"]
        pdf = text_layer_pdf(contents or FORMAL_REPORT_PAGES)
        assert client.post(
            f"/api/assessments/{aid}/document", headers=coord_headers,
            files={"file": ("report.pdf", pdf, "application/pdf")},
        ).status_code == 200
        assert client.post(f"/api/assessments/{aid}/process", headers=coord_headers).status_code == 202
        process_one(factory, storage, NoOcr())
        db_session.expire_all()
        if finalize:
            r = client.patch(f"/api/assessments/{aid}/status", headers=coord_headers, json={"status": "finalized"})
            assert r.status_code == 200, r.text
        return learner, aid

    return _make


def run(client, headers, aid):
    return client.post(f"/api/assessments/{aid}/extractions", headers=headers)


def test_extraction_requires_finalized(client, coord_headers, finalized):
    _, aid = finalized(finalize=False)
    response = run(client, coord_headers, aid)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "assessment_not_finalized"


def test_run_edit_approve_flow(client, coord_headers, coordinator, finalized):
    learner, aid = finalized()
    response = run(client, coord_headers, aid)
    assert response.status_code == 201, response.text
    v1 = response.json()
    assert v1["version_number"] == 1 and v1["status"] == "draft" and v1["method"] == "rule"
    assert v1["extractor_version"] == "rules-1" and not v1["is_stale"]
    assert v1["finding_count"] == len(v1["findings"]) > 0
    diagnosis = next(f for f in v1["findings"] if f["category"] == "diagnosis")
    assert diagnosis["source_page"] == 1 and diagnosis["origin"] == "extracted"

    # A second run while a draft is open is refused.
    assert run(client, coord_headers, aid).json()["error"]["code"] == "draft_exists"

    vid = v1["id"]
    edited = client.patch(
        f"/api/extractions/{vid}/findings/{diagnosis['id']}", headers=coord_headers,
        json={"text": "Autism Spectrum Disorder, Level 1 (with language delay)."},
    ).json()
    assert edited["edited"] is True and edited["source_quote"]  # source kept

    added = client.post(
        f"/api/extractions/{vid}/findings", headers=coord_headers,
        json={"category": "strength", "domain": "motor", "text": "Enjoys drawing."},
    )
    assert added.status_code == 201
    assert added.json()["origin"] == "manual" and added.json()["source_page"] is None

    to_delete = next(f for f in v1["findings"] if f["category"] == "recommendation")
    assert client.delete(f"/api/extractions/{vid}/findings/{to_delete['id']}", headers=coord_headers).status_code == 204

    # Nothing is available for goal matching until approval.
    assert client.get(f"/api/learners/{learner['id']}/findings", headers=coord_headers).json()["items"] == []

    approved = client.post(f"/api/extractions/{vid}/approve", headers=coord_headers)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["approved_by_name"] == coordinator.name

    items = client.get(f"/api/learners/{learner['id']}/findings", headers=coord_headers).json()["items"]
    texts = [i["text"] for i in items]
    assert "Enjoys drawing." in texts
    assert to_delete["text"] not in texts
    assert all(i["version_id"] == vid and i["stale"] is False for i in items)

    assessment = client.get(f"/api/assessments/{aid}", headers=coord_headers).json()
    assert assessment["approved_findings_count"] == len(items)

    # Approved versions are read-only.
    response = client.patch(
        f"/api/extractions/{vid}/findings/{diagnosis['id']}", headers=coord_headers, json={"text": "x"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "version_not_draft"
    assert client.delete(f"/api/extractions/{vid}", headers=coord_headers).status_code == 409


def test_new_version_supersedes_old_only_when_approved(client, coord_headers, finalized):
    learner, aid = finalized()
    v1 = run(client, coord_headers, aid).json()
    client.post(f"/api/extractions/{v1['id']}/approve", headers=coord_headers)

    v2 = run(client, coord_headers, aid).json()
    assert v2["version_number"] == 2 and v2["status"] == "draft"
    # v1 is still the approved one while v2 is a draft.
    items = client.get(f"/api/learners/{learner['id']}/findings", headers=coord_headers).json()["items"]
    assert {i["version_id"] for i in items} == {v1["id"]}

    client.post(f"/api/extractions/{v2['id']}/approve", headers=coord_headers)
    versions = client.get(f"/api/assessments/{aid}/extractions", headers=coord_headers).json()["items"]
    assert [(v["version_number"], v["status"]) for v in versions] == [(2, "approved"), (1, "superseded")]
    items = client.get(f"/api/learners/{learner['id']}/findings", headers=coord_headers).json()["items"]
    assert {i["version_id"] for i in items} == {v2["id"]}


def test_copy_to_draft(client, coord_headers, finalized):
    _, aid = finalized()
    v1 = run(client, coord_headers, aid).json()
    client.post(f"/api/extractions/{v1['id']}/approve", headers=coord_headers)

    copy = client.post(f"/api/extractions/{v1['id']}/copy", headers=coord_headers)
    assert copy.status_code == 201
    data = copy.json()
    assert data["method"] == "manual" and data["based_on_version_id"] == v1["id"] and data["status"] == "draft"
    assert [f["text"] for f in data["findings"]] == [f["text"] for f in v1["findings"]]
    assert client.post(f"/api/extractions/{v1['id']}/copy", headers=coord_headers).status_code == 409

    assert client.delete(f"/api/extractions/{data['id']}", headers=coord_headers).status_code == 204
    versions = client.get(f"/api/assessments/{aid}/extractions", headers=coord_headers).json()["items"]
    assert [v["status"] for v in versions] == ["approved"]


def test_reorder(client, coord_headers, finalized):
    _, aid = finalized()
    v1 = run(client, coord_headers, aid).json()
    ids = [f["id"] for f in v1["findings"]]
    reordered = client.put(
        f"/api/extractions/{v1['id']}/order", headers=coord_headers, json={"finding_ids": list(reversed(ids))}
    )
    assert reordered.status_code == 200
    assert [f["id"] for f in reordered.json()["findings"]] == list(reversed(ids))
    bad = client.put(f"/api/extractions/{v1['id']}/order", headers=coord_headers, json={"finding_ids": ids[:2]})
    assert bad.status_code == 422


def test_stale_source_blocks_approval(client, coord_headers, finalized, db_session):
    learner, aid = finalized()
    v1 = run(client, coord_headers, aid).json()
    client.post(f"/api/extractions/{v1['id']}/approve", headers=coord_headers)
    v2 = run(client, coord_headers, aid).json()

    # Reopen, correct the OCR text, finalize again.
    client.patch(f"/api/assessments/{aid}/status", headers=coord_headers, json={"status": "needs_review"})
    r = client.put(f"/api/assessments/{aid}/ocr/pages/1", headers=coord_headers, json={"reviewed_text": "Changed text."})
    assert r.status_code == 200
    client.patch(f"/api/assessments/{aid}/status", headers=coord_headers, json={"status": "finalized"})

    detail = client.get(f"/api/extractions/{v2['id']}", headers=coord_headers).json()
    assert detail["is_stale"] is True
    response = client.post(f"/api/extractions/{v2['id']}/approve", headers=coord_headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "source_changed"
    # The previously approved findings remain, flagged as stale.
    items = client.get(f"/api/learners/{learner['id']}/findings", headers=coord_headers).json()["items"]
    assert items and all(i["stale"] for i in items)


def test_extraction_permissions(client, make_user, login, coord_headers, finalized):
    learner, aid = finalized()
    v1 = run(client, coord_headers, aid).json()
    vid = v1["id"]

    teacher = make_user(Role.TEACHER)
    client.post(f"/api/learners/{learner['id']}/assignments", headers=coord_headers, json={"user_id": teacher.id})
    assigned = login(teacher)
    assert client.post(
        f"/api/extractions/{vid}/findings", headers=assigned, json={"category": "need", "text": "Needs help."}
    ).status_code == 201
    assert client.post(f"/api/extractions/{vid}/approve", headers=assigned).status_code == 403

    head = login(make_user(Role.SCHOOL_HEAD))
    assert client.get(f"/api/extractions/{vid}", headers=head).status_code == 200
    assert client.get(f"/api/learners/{learner['id']}/findings", headers=head).status_code == 200
    assert run(client, head, aid).status_code == 403
    assert client.post(f"/api/extractions/{vid}/findings", headers=head, json={"category": "need", "text": "x"}).status_code == 403

    stranger = login(make_user(Role.TEACHER))
    assert client.get(f"/api/extractions/{vid}", headers=stranger).status_code == 404
    assert client.get(f"/api/assessments/{aid}/extractions", headers=stranger).status_code == 404
    assert client.get(f"/api/learners/{learner['id']}/findings", headers=stranger).status_code == 404

    admin = login(make_user(Role.SYSTEM_ADMIN))
    assert client.get(f"/api/extractions/{vid}", headers=admin).status_code == 403
    assert client.get(f"/api/extractions/{vid}").status_code == 401


def test_finding_validation(client, coord_headers, finalized):
    _, aid = finalized()
    vid = run(client, coord_headers, aid).json()["id"]
    url = f"/api/extractions/{vid}/findings"
    assert client.post(url, headers=coord_headers, json={"category": "wish", "text": "x"}).status_code == 422
    assert client.post(url, headers=coord_headers, json={"category": "need", "text": "   "}).status_code == 422
    assert client.post(url, headers=coord_headers, json={"category": "need", "text": "x" * 2001}).status_code == 422


def test_ocr_text_is_what_gets_extracted(client, coord_headers, finalized, db_session):
    """Extraction uses the reviewed text when there is one."""
    _, aid = finalized(contents=REPORT_PAGES)
    page = db_session.scalars(select(OcrPage).order_by(OcrPage.page_number)).first()
    assert "READING" in page.raw_text
    findings = run(client, coord_headers, aid).json()["findings"]
    assert any(f["category"] == "present_level" and f["domain"] == "reading" for f in findings)
