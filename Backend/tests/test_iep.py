"""Stage 9: IEP builder - import, editing, validation, finalize, amendments, DOCX."""

import io
from datetime import date

import pytest
from docx import Document
from sqlalchemy import func, select

from app.models.goal import GoalUsage
from app.models.iep import Iep
from app.models.user import Role
from test_matching import (  # noqa: F401  (pytest fixtures reused from the matching tests)
    FakeEmbedder,
    bank,
    coord_headers,
    coordinator,
    embedder,
    learner_with_needs,
)

TEAM = [{"name": "Ana Cruz", "role": "SNED Coordinator"}, {"name": "Ben Reyes", "role": "Adviser"}]


@pytest.fixture
def prepared(client, coord_headers, bank, learner_with_needs, embedder):
    """Learner with approved needs and one accepted (edited) goal suggestion."""

    def _make(code="IEP-1"):
        learner = learner_with_needs(code=code)
        run = client.post(f"/api/learners/{learner['id']}/matching-runs", headers=coord_headers, json={"min_score": 0}).json()
        rec = run["needs"][0]["suggestions"][0]
        client.post(f"/api/recommendations/{rec['id']}/accept", headers=coord_headers,
                    json={"edited_target_value": 70, "edited_criterion": "across 3 sessions"})
        return learner, run, rec

    return _make


def create(client, headers, learner_id):
    response = client.post(f"/api/learners/{learner_id}/ieps", headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def complete(client, headers, iep):
    """Fill every required field so the IEP validates."""
    iep_id = iep["id"]
    client.patch(f"/api/ieps/{iep_id}", headers=headers, json={"team_members": TEAM, "accommodations": "Extra time."})
    for goal in iep["goals"]:
        r = client.patch(f"/api/ieps/{iep_id}/goals/{goal['id']}", headers=headers,
                         json={"baseline": "Solves 3 of 10 subtraction facts (30%).", "baseline_value": 30,
                               "responsible_staff": "Ben Reyes (adviser)"})
        assert r.status_code == 200, r.text
    return client.get(f"/api/ieps/{iep_id}", headers=headers).json()


# --- Create and import ------------------------------------------------------------------


def test_create_imports_findings_and_accepted_goals(client, coord_headers, prepared, db_session):
    learner, run, rec = prepared()
    result = client.post(f"/api/learners/{learner['id']}/ieps", headers=coord_headers)
    assert result.status_code == 201, result.text
    body = result.json()
    iep = body["iep"]
    assert body["findings_added"] == 4  # 2 needs + strength + recommendation (approved only)
    assert body["goals_added"] == 1
    assert iep["version_number"] == 1 and iep["status"] == "draft" and iep["read_only"] is False
    assert iep["school_year"] == "2025-2026"
    assert iep["end_date"] == "2026-05-31" and iep["annual_review_date"] == "2026-05-17"
    assert {f["text"] for f in iep["findings"]} >= {"Has difficulty with subtraction and word problems.", "Recognizes all letters."}
    assert all("Draft need" not in f["text"] for f in iep["findings"])

    goal = iep["goals"][0]
    assert goal["source"] == "accepted_recommendation" and goal["goal_recommendation_id"] == rec["id"]
    assert goal["statement"] == rec["goal_version"]["statement"]
    assert goal["target_value"] == 70 and goal["criterion"] == "across 3 sessions"  # edited wording
    assert goal["goal_code"] == rec["goal_code"] and goal["match_score"] == rec["score"]
    assert goal["baseline"].startswith("From assessment:")
    assert len(goal["review_dates"]) == 4 and goal["review_dates"][-1] == "2026-05-31"
    need = next(f for f in iep["findings"] if f["id"] == goal["addresses_finding_id"])
    assert need["text"] == "Has difficulty with subtraction and word problems."
    assert db_session.scalar(select(func.count(GoalUsage.id)).where(GoalUsage.usage_type == "iep_goal")) == 1

    # Re-import adds nothing new; a second draft is refused.
    again = client.post(f"/api/ieps/{iep['id']}/import", headers=coord_headers).json()
    assert (again["findings_added"], again["goals_added"]) == (0, 0)
    dup = client.post(f"/api/learners/{learner['id']}/ieps", headers=coord_headers)
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "draft_exists"

    # A goal accepted later is picked up by re-import.
    second = run["needs"][1]["suggestions"][0]
    client.post(f"/api/recommendations/{second['id']}/accept", headers=coord_headers, json={})
    assert client.post(f"/api/ieps/{iep['id']}/import", headers=coord_headers).json()["goals_added"] == 1


# --- Editing ----------------------------------------------------------------------------


def test_edit_goals_and_findings(client, coord_headers, prepared, bank):
    learner, _, _ = prepared()
    iep = create(client, coord_headers, learner["id"])["iep"]
    iid = iep["id"]
    goal = iep["goals"][0]

    updated = client.patch(f"/api/ieps/{iid}/goals/{goal['id']}", headers=coord_headers, json={
        "baseline": "3/10", "baseline_value": 30, "target_value": 80, "responsible_staff": "Adviser; parent",
        "review_dates": ["2025-09-30", "2025-12-15"], "target_date": "2026-03-31",
    }).json()
    assert updated["review_dates"] == ["2025-09-30", "2025-12-15"] and updated["target_value"] == 80
    bad = client.patch(f"/api/ieps/{iid}/goals/{goal['id']}", headers=coord_headers, json={"review_dates": ["not-a-date"]})
    assert bad.status_code == 422

    from_bank = client.post(f"/api/ieps/{iid}/goals", headers=coord_headers, json={"goal_id": bank["MO-001"].id})
    assert from_bank.status_code == 201 and from_bank.json()["source"] == "goal_bank"
    assert from_bank.json()["goal_code"] == "MO-001" and len(from_bank.json()["review_dates"]) == 4
    custom = client.post(f"/api/ieps/{iid}/goals", headers=coord_headers, json={
        "statement": "The learner will greet two classmates each morning on 4 of 5 days.", "domain": "behavior_social",
        "measurement_method": "frequency", "target_value": 4, "target_unit": "count",
    })
    assert custom.status_code == 201 and custom.json()["source"] == "custom"
    assert client.post(f"/api/ieps/{iid}/goals", headers=coord_headers, json={"domain": "motor"}).status_code == 422

    ids = [g["id"] for g in client.get(f"/api/ieps/{iid}", headers=coord_headers).json()["goals"]]
    reordered = client.put(f"/api/ieps/{iid}/goals/order", headers=coord_headers, json={"ids": ids[::-1]}).json()
    assert [g["id"] for g in reordered["goals"]] == ids[::-1]
    assert client.delete(f"/api/ieps/{iid}/goals/{custom.json()['id']}", headers=coord_headers).status_code == 204

    f = client.post(f"/api/ieps/{iid}/findings", headers=coord_headers,
                    json={"category": "present_level", "domain": "motor", "text": "Uses a fist grip."}).json()
    assert client.patch(f"/api/ieps/{iid}/findings/{f['id']}", headers=coord_headers,
                        json={"text": "Uses a fist grip when writing."}).json()["text"] == "Uses a fist grip when writing."
    # Deleting a finding unlinks goals that pointed at it.
    client.patch(f"/api/ieps/{iid}/goals/{goal['id']}", headers=coord_headers, json={"addresses_finding_id": f["id"]})
    client.delete(f"/api/ieps/{iid}/findings/{f['id']}", headers=coord_headers)
    goal_now = next(g for g in client.get(f"/api/ieps/{iid}", headers=coord_headers).json()["goals"] if g["id"] == goal["id"])
    assert goal_now["addresses_finding_id"] is None


# --- Validation and finalize ----------------------------------------------------------------


def test_validation_and_finalize(client, coord_headers, prepared, coordinator):
    learner, _, _ = prepared()
    iep = create(client, coord_headers, learner["id"])["iep"]
    iid = iep["id"]
    fields = {i["field"] for i in iep["validation"]}
    goal_id = iep["goals"][0]["id"]
    assert "team_members" in fields and f"goals.{goal_id}.responsible_staff" in fields
    assert f"goals.{goal_id}.baseline" not in fields  # pre-filled from assessment

    # Dates outside the period are caught.
    client.patch(f"/api/ieps/{iid}/goals/{goal_id}", headers=coord_headers,
                 json={"review_dates": ["2027-01-01"], "baseline": ""})
    issues = {i["field"] for i in client.get(f"/api/ieps/{iid}/validation", headers=coord_headers).json()}
    assert {f"goals.{goal_id}.review_dates", f"goals.{goal_id}.baseline"} <= issues

    response = client.post(f"/api/ieps/{iid}/finalize", headers=coord_headers)
    assert response.status_code == 422 and response.json()["error"]["code"] == "iep_invalid"
    assert any(d["field"] == "team_members" for d in response.json()["error"]["details"])

    client.patch(f"/api/ieps/{iid}/goals/{goal_id}", headers=coord_headers, json={"review_dates": ["2025-10-15", "2026-05-31"]})
    ready = complete(client, coord_headers, client.get(f"/api/ieps/{iid}", headers=coord_headers).json())
    assert ready["validation"] == []
    final = client.post(f"/api/ieps/{iid}/finalize", headers=coord_headers)
    assert final.status_code == 200, final.text
    assert final.json()["status"] == "finalized" and final.json()["read_only"] is True
    assert final.json()["finalized_by_name"] == coordinator.name

    # A second IEP for the same year must be an amendment.
    dup = client.post(f"/api/learners/{learner['id']}/ieps", headers=coord_headers)
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "iep_exists"


def test_finalized_iep_is_read_only(client, coord_headers, prepared, bank):
    learner, _, _ = prepared()
    iep = complete(client, coord_headers, create(client, coord_headers, learner["id"])["iep"])
    iid = iep["id"]
    assert client.post(f"/api/ieps/{iid}/finalize", headers=coord_headers).status_code == 200
    goal_id, finding_id = iep["goals"][0]["id"], iep["findings"][0]["id"]
    attempts = [
        client.patch(f"/api/ieps/{iid}", headers=coord_headers, json={"notes": "x"}),
        client.post(f"/api/ieps/{iid}/import", headers=coord_headers),
        client.delete(f"/api/ieps/{iid}", headers=coord_headers),
        client.patch(f"/api/ieps/{iid}/goals/{goal_id}", headers=coord_headers, json={"baseline": "x"}),
        client.delete(f"/api/ieps/{iid}/goals/{goal_id}", headers=coord_headers),
        client.post(f"/api/ieps/{iid}/goals", headers=coord_headers, json={"goal_id": bank["MO-001"].id}),
        client.put(f"/api/ieps/{iid}/goals/order", headers=coord_headers, json={"ids": [goal_id]}),
        client.post(f"/api/ieps/{iid}/findings", headers=coord_headers, json={"category": "need", "text": "x"}),
        client.patch(f"/api/ieps/{iid}/findings/{finding_id}", headers=coord_headers, json={"text": "x"}),
        client.delete(f"/api/ieps/{iid}/findings/{finding_id}", headers=coord_headers),
        client.post(f"/api/ieps/{iid}/finalize", headers=coord_headers),
    ]
    for response in attempts:
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "iep_read_only"


# --- Amendments ----------------------------------------------------------------------------------


def test_amendment_creates_new_version(client, coord_headers, prepared, db_session):
    learner, _, _ = prepared()
    v1 = complete(client, coord_headers, create(client, coord_headers, learner["id"])["iep"])
    client.post(f"/api/ieps/{v1['id']}/finalize", headers=coord_headers)

    assert client.post(f"/api/ieps/{v1['id']}/amend", headers=coord_headers, json={"reason": ""}).status_code == 422
    v2 = client.post(f"/api/ieps/{v1['id']}/amend", headers=coord_headers, json={"reason": "Target raised after review."})
    assert v2.status_code == 201, v2.text
    v2 = v2.json()
    assert v2["version_number"] == 2 and v2["status"] == "draft" and v2["amends_iep_id"] == v1["id"]
    assert v2["amendment_reason"] == "Target raised after review."
    assert [g["statement"] for g in v2["goals"]] == [g["statement"] for g in v1["goals"]]
    assert [f["text"] for f in v2["findings"]] == [f["text"] for f in v1["findings"]]
    linked = [g["addresses_finding_id"] for g in v2["goals"] if g["addresses_finding_id"]]
    assert linked and set(linked) <= {f["id"] for f in v2["findings"]}  # remapped to the copies
    assert client.get(f"/api/ieps/{v1['id']}", headers=coord_headers).json()["status"] == "finalized"
    assert client.post(f"/api/ieps/{v1['id']}/amend", headers=coord_headers, json={"reason": "Again please"}).status_code == 409

    client.patch(f"/api/ieps/{v2['id']}/goals/{v2['goals'][0]['id']}", headers=coord_headers, json={"target_value": 85})
    assert client.post(f"/api/ieps/{v2['id']}/finalize", headers=coord_headers).status_code == 200
    v1_now = client.get(f"/api/ieps/{v1['id']}", headers=coord_headers).json()
    assert v1_now["status"] == "superseded" and v1_now["goals"][0]["target_value"] == 70
    assert client.post(f"/api/ieps/{v1['id']}/amend", headers=coord_headers, json={"reason": "Old version"}).status_code == 409

    history = client.get(f"/api/learners/{learner['id']}/ieps", headers=coord_headers).json()["items"]
    assert [(h["version_number"], h["status"]) for h in history] == [(2, "finalized"), (1, "superseded")]

    summary = client.get(f"/api/learners/{learner['id']}/summary", headers=coord_headers).json()["modules"]["iep"]
    assert summary["available"] is True and summary["count"] == 2 and summary["latest_status"] == "finalized"


def test_amendment_reason_is_validated(client, coord_headers, prepared, db_session):
    learner, _, _ = prepared()
    v1 = complete(client, coord_headers, create(client, coord_headers, learner["id"])["iep"])
    client.post(f"/api/ieps/{v1['id']}/finalize", headers=coord_headers)
    v2 = client.post(f"/api/ieps/{v1['id']}/amend", headers=coord_headers, json={"reason": "New goal added"}).json()
    client.patch(f"/api/ieps/{v2['id']}", headers=coord_headers, json={"amendment_reason": None})
    fields = {i["field"] for i in client.get(f"/api/ieps/{v2['id']}/validation", headers=coord_headers).json()}
    assert "amendment_reason" in fields


# --- DOCX ------------------------------------------------------------------------------------------


def _docx_text(content: bytes) -> str:
    doc = Document(io.BytesIO(content))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.extend(cell.text for cell in row.cells)
    parts.extend(p.text for p in doc.sections[0].header.paragraphs)
    parts.extend(p.text for p in doc.sections[0].footer.paragraphs)
    return "\n".join(parts)


def test_docx_generated_from_record(client, coord_headers, prepared):
    learner, _, _ = prepared()
    iep = complete(client, coord_headers, create(client, coord_headers, learner["id"])["iep"])
    draft = client.get(f"/api/ieps/{iep['id']}/document", headers=coord_headers)
    assert draft.status_code == 200
    assert draft.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.wordprocessingml")
    assert "_DRAFT.docx" in draft.headers["content-disposition"]
    text = _docx_text(draft.content)
    assert "DRAFT – NOT FINAL" in text
    assert "INDIVIDUALIZED EDUCATION PROGRAM (IEP)" in text
    assert learner["full_name"] in text and learner["learner_code"] in text
    assert iep["goals"][0]["statement"] in text
    assert "Solves 3 of 10 subtraction facts (30%)." in text
    assert "70% across 3 sessions" in text
    assert "Ana Cruz" in text and "Parent / guardian" in text
    assert "Has difficulty with subtraction and word problems." in text

    client.post(f"/api/ieps/{iep['id']}/finalize", headers=coord_headers)
    final = client.get(f"/api/ieps/{iep['id']}/document", headers=coord_headers)
    text = _docx_text(final.content)
    assert "DRAFT – NOT FINAL" not in text and "Finalized" in text
    assert final.headers["content-disposition"].endswith('_v1.docx"')


# --- Permissions ----------------------------------------------------------------------------------


def test_iep_permissions(client, coord_headers, prepared, make_user, login):
    learner, _, _ = prepared()
    teacher = make_user(Role.TEACHER)
    client.post(f"/api/learners/{learner['id']}/assignments", headers=coord_headers, json={"user_id": teacher.id})
    assigned = login(teacher)

    iep = create(client, assigned, learner["id"])["iep"]  # teachers can create drafts
    iep = complete(client, assigned, iep)
    assert client.post(f"/api/ieps/{iep['id']}/finalize", headers=assigned).status_code == 403
    client.post(f"/api/ieps/{iep['id']}/finalize", headers=coord_headers)
    assert client.post(f"/api/ieps/{iep['id']}/amend", headers=assigned, json={"reason": "Teacher wants changes"}).status_code == 403

    head = login(make_user(Role.SCHOOL_HEAD))
    assert client.get(f"/api/ieps/{iep['id']}", headers=head).status_code == 200
    assert client.get(f"/api/ieps/{iep['id']}/document", headers=head).status_code == 200
    assert client.get(f"/api/learners/{learner['id']}/ieps", headers=head).status_code == 200
    assert client.patch(f"/api/ieps/{iep['id']}", headers=head, json={"notes": "x"}).status_code == 403
    assert client.post(f"/api/learners/{learner['id']}/ieps", headers=head).status_code == 403

    stranger = login(make_user(Role.TEACHER))
    assert client.get(f"/api/ieps/{iep['id']}", headers=stranger).status_code == 404
    assert client.get(f"/api/ieps/{iep['id']}/document", headers=stranger).status_code == 404
    assert client.get(f"/api/ieps/{iep['id']}").status_code == 401


def test_discard_draft(client, coord_headers, prepared, db_session):
    learner, _, _ = prepared()
    iep = create(client, coord_headers, learner["id"])["iep"]
    assert client.delete(f"/api/ieps/{iep['id']}", headers=coord_headers).status_code == 204
    assert db_session.get(Iep, iep["id"]) is None
    # A new draft can be created afterwards.
    assert create(client, coord_headers, learner["id"])["iep"]["version_number"] == 1


def test_default_period_and_quarterly_reviews():
    from app.services.iep_service import default_period, quarterly_reviews, school_year_period

    assert school_year_period("2025-2026") == (date(2025, 6, 1), date(2026, 5, 31))
    assert default_period("2025-2026", today=date(2025, 8, 20)) == (date(2025, 8, 20), date(2026, 5, 31))
    assert default_period("2025-2026", today=date(2027, 1, 1)) == (date(2025, 6, 1), date(2026, 5, 31))
    dates = quarterly_reviews(date(2025, 6, 1), date(2026, 5, 31))
    assert dates[0] < dates[1] < dates[2] < dates[3] == "2026-05-31"
