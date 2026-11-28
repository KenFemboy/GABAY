"""Stage 10: ILAW activity log and alignment with the active IEP's goals."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.main import app
from app.models.ilaw import IlawAlignment, IlawEntry
from app.models.user import Role
from app.services import embedding_service
from app.services.embedding_service import get_embedder
from test_iep import complete, create, prepared  # noqa: F401  (fixtures + helpers)
from test_matching import (  # noqa: F401
    FakeEmbedder,
    bank,
    coord_headers,
    coordinator,
    embedder,
    learner_with_needs,
)

MATH = "Subtraction practice with counters"
MATH_TEXT = "The learner solved single-digit subtraction problems with counters and word problems."


@pytest.fixture
def active(client, coord_headers, prepared, bank):
    """Learner with a FINALIZED IEP holding three goals: math (accepted), motor (bank), behavior (custom)."""

    def _make(code="ILAW-1"):
        learner, _, _ = prepared(code=code)
        iep = create(client, coord_headers, learner["id"])["iep"]
        client.post(f"/api/ieps/{iep['id']}/goals", headers=coord_headers, json={"goal_id": bank["MO-001"].id})
        client.post(f"/api/ieps/{iep['id']}/goals", headers=coord_headers, json={
            "statement": "During recess the learner will greet and invite a classmate to play on 4 of 5 days.",
            "domain": "behavior_social", "measurement_method": "frequency", "target_value": 4, "target_unit": "count",
        })
        iep = complete(client, coord_headers, client.get(f"/api/ieps/{iep['id']}", headers=coord_headers).json())
        assert iep["validation"] == [], iep["validation"]
        final = client.post(f"/api/ieps/{iep['id']}/finalize", headers=coord_headers)
        assert final.status_code == 200, final.text
        return learner, final.json()

    return _make


def log(client, headers, learner_id, **overrides):
    body = {"activity_date": "2025-09-15", "title": MATH, "description": MATH_TEXT,
            "learner_response": "Solved 6 of 10 with help.", "duration_minutes": 30}
    body.update(overrides)
    return client.post(f"/api/learners/{learner_id}/ilaw", headers=headers, json=body)


def goal_by_domain(iep, domain):
    return next(g for g in iep["goals"] if g["domain"] == domain)


# --- Active IEP rule ---------------------------------------------------------------------


def test_requires_finalized_iep(client, coord_headers, prepared):
    learner, _, _ = prepared(code="NOIEP")
    response = log(client, coord_headers, learner["id"])
    assert response.status_code == 409 and response.json()["error"]["code"] == "no_active_iep"
    create(client, coord_headers, learner["id"])  # a draft is not enough
    assert log(client, coord_headers, learner["id"]).status_code == 409
    assert client.get(f"/api/learners/{learner['id']}/ilaw/active-iep", headers=coord_headers).json() == {"iep": None}


def test_create_entry_with_suggestions(client, coord_headers, active, coordinator):
    learner, iep = active()
    active_iep = client.get(f"/api/learners/{learner['id']}/ilaw/active-iep", headers=coord_headers).json()["iep"]
    assert active_iep["id"] == iep["id"] and len(active_iep["goals"]) == 3

    response = log(client, coord_headers, learner["id"])
    assert response.status_code == 201, response.text
    entry = response.json()
    assert entry["iep_id"] == iep["id"] and entry["created_by_name"] == coordinator.name
    assert entry["suggestions_error"] is None
    links = entry["alignments"]
    assert links, "expected at least one suggestion"
    goal_ids = {g["id"] for g in iep["goals"]}
    assert all(l["iep_goal_id"] in goal_ids for l in links)
    assert [l["rank"] for l in links] == list(range(1, len(links) + 1))
    assert all(l["status"] == "suggested" and l["source"] == "suggested" for l in links)
    assert all(l["model_version"] == "fake-bow-384|ilaw-text-v1" and l["score"] >= 0.35 for l in links)
    assert links[0]["goal"]["domain"] == "mathematics"  # shares the most words with the entry

    # Profile summary shows the module.
    summary = client.get(f"/api/learners/{learner['id']}/summary", headers=coord_headers).json()["modules"]["ilaw"]
    assert summary["available"] is True and summary["count"] == 1


# --- Duplicates and dates ----------------------------------------------------------------


def test_duplicate_entries_are_refused(client, coord_headers, active, db_session):
    learner, _ = active()
    first = log(client, coord_headers, learner["id"]).json()
    dup = log(client, coord_headers, learner["id"], title="  subtraction   PRACTICE with Counters ")
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "duplicate_entry"
    other_day = log(client, coord_headers, learner["id"], activity_date="2025-09-16")
    assert other_day.status_code == 201
    other_title = log(client, coord_headers, learner["id"], title="Counting to 50")
    assert other_title.status_code == 201
    # An update that would collide is refused too.
    clash = client.patch(f"/api/ilaw/{other_title.json()['id']}", headers=coord_headers, json={"title": MATH.upper()})
    assert clash.status_code == 409
    # Renaming to itself is fine.
    assert client.patch(f"/api/ilaw/{first['id']}", headers=coord_headers, json={"title": MATH}).status_code == 200

    # The database constraint holds even if the service check is bypassed.
    original = db_session.get(IlawEntry, first["id"])
    db_session.add(IlawEntry(learner_id=original.learner_id, iep_id=original.iep_id, activity_date=original.activity_date,
                             title="x", title_key=original.title_key, description="x", created_by=original.created_by))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_date_rules(client, coord_headers, active):
    learner, _ = active()
    future = log(client, coord_headers, learner["id"], activity_date="2099-01-01")
    assert future.status_code == 422 and future.json()["error"]["code"] == "future_date"
    outside = log(client, coord_headers, learner["id"], activity_date="2025-01-10")
    assert outside.status_code == 422 and outside.json()["error"]["code"] == "outside_iep_period"
    assert log(client, coord_headers, learner["id"], title="  ").status_code == 422


# --- Decisions -----------------------------------------------------------------------------


def test_confirm_reject_change_and_manual(client, coord_headers, active, coordinator, db_session, monkeypatch):
    # The fake embedder is crude; drop the threshold so several goals are suggested.
    monkeypatch.setattr(get_settings(), "ilaw_min_score", 0.0)
    learner, iep = active()
    entry = log(client, coord_headers, learner["id"], description=MATH_TEXT + " Then traced shapes with a pencil.").json()
    links = entry["alignments"]
    assert len(links) >= 2
    first, second = links[0], links[1]

    confirmed = client.post(f"/api/ilaw-links/{first['id']}/confirm", headers=coord_headers).json()
    assert confirmed["status"] == "confirmed" and confirmed["decided_by_name"] == coordinator.name and confirmed["decided_at"]
    rejected = client.post(f"/api/ilaw-links/{second['id']}/reject", headers=coord_headers).json()
    assert rejected["status"] == "rejected"
    assert client.post(f"/api/ilaw-links/{second['id']}/reset", headers=coord_headers).status_code == 204
    assert db_session.get(IlawAlignment, second["id"]).status == "suggested"

    # Change: reject the suggestion and confirm another active goal instead.
    behavior = goal_by_domain(iep, "behavior_social")
    changed = client.post(f"/api/ilaw-links/{second['id']}/change", headers=coord_headers, json={"iep_goal_id": behavior["id"]})
    assert changed.status_code == 200, changed.text
    assert changed.json()["iep_goal_id"] == behavior["id"] and changed.json()["status"] == "confirmed"
    detail = client.get(f"/api/ilaw/{entry['id']}", headers=coord_headers).json()
    by_goal = {l["iep_goal_id"]: l for l in detail["alignments"]}
    assert by_goal[second["iep_goal_id"]]["status"] == "rejected"

    # Manual link to a goal that is not in the active IEP is refused.
    assert client.post(f"/api/ilaw/{entry['id']}/links", headers=coord_headers, json={"iep_goal_id": 999999}).status_code == 422

    # Re-suggest keeps every decision and never duplicates rows.
    before = db_session.scalar(select(func.count(IlawAlignment.id)).where(IlawAlignment.entry_id == entry["id"]))
    again = client.post(f"/api/ilaw/{entry['id']}/suggest", headers=coord_headers).json()
    after = db_session.scalar(select(func.count(IlawAlignment.id)).where(IlawAlignment.entry_id == entry["id"]))
    assert after <= before + 1 and len({l["iep_goal_id"] for l in again["alignments"]}) == len(again["alignments"])
    statuses = {l["iep_goal_id"]: l["status"] for l in again["alignments"]}
    assert statuses[first["iep_goal_id"]] == "confirmed"
    assert statuses[second["iep_goal_id"]] == "rejected"
    assert statuses[behavior["id"]] == "confirmed"

    # Goal filter lists entries with a confirmed link to that goal.
    listed = client.get(f"/api/learners/{learner['id']}/ilaw", headers=coord_headers, params={"goal": behavior["id"]}).json()
    assert [e["id"] for e in listed["items"]] == [entry["id"]]


def test_update_resuggests_and_keeps_decisions(client, coord_headers, active):
    learner, iep = active()
    entry = log(client, coord_headers, learner["id"]).json()
    top = entry["alignments"][0]
    client.post(f"/api/ilaw-links/{top['id']}/confirm", headers=coord_headers)
    updated = client.patch(f"/api/ilaw/{entry['id']}", headers=coord_headers, json={
        "description": "Pencil grip practice: tracing lines and shapes with a tripod grasp."}).json()
    by_goal = {l["iep_goal_id"]: l for l in updated["alignments"]}
    assert by_goal[top["iep_goal_id"]]["status"] == "confirmed"
    motor = goal_by_domain(iep, "motor")
    assert motor["id"] in by_goal  # new text now suggests the motor goal


# --- Active IEP only (amendments) ----------------------------------------------------------------


def test_only_active_iep_goals_after_amendment(client, coord_headers, active):
    learner, v1 = active()
    entry = log(client, coord_headers, learner["id"]).json()
    top = entry["alignments"][0]
    client.post(f"/api/ilaw-links/{top['id']}/confirm", headers=coord_headers)

    # An amendment DRAFT does not change the active IEP.
    v2 = client.post(f"/api/ieps/{v1['id']}/amend", headers=coord_headers, json={"reason": "New behavior goal wording"}).json()
    again = client.post(f"/api/ilaw/{entry['id']}/suggest", headers=coord_headers).json()
    assert again["iep_id"] == v1["id"]
    assert {l["iep_goal_id"] for l in again["alignments"]} <= {g["id"] for g in v1["goals"]}

    # After the amendment is finalized, re-suggesting moves the entry to v2.
    assert client.post(f"/api/ieps/{v2['id']}/finalize", headers=coord_headers).status_code == 200
    moved = client.post(f"/api/ilaw/{entry['id']}/suggest", headers=coord_headers).json()
    assert moved["iep_id"] == v2["id"]
    v2_ids = {g["id"] for g in v2["goals"]}
    pending = [l for l in moved["alignments"] if l["status"] == "suggested"]
    assert pending and all(l["iep_goal_id"] in v2_ids for l in pending)
    # The confirmed link on the old version stays as history.
    assert any(l["iep_goal_id"] == top["iep_goal_id"] and l["status"] == "confirmed" for l in moved["alignments"])
    # New entries use v2.
    new = log(client, coord_headers, learner["id"], title="Number line game", activity_date="2025-10-01").json()
    assert new["iep_id"] == v2["id"]


# --- Model unavailable ------------------------------------------------------------------------------


def test_entry_saved_when_model_unavailable(client, coord_headers, active):
    learner, _ = active()

    class Broken:
        model = "broken"

        def embed(self, texts):
            raise embedding_service.EmbeddingUnavailable("offline")

    fake = app.dependency_overrides[get_embedder]
    app.dependency_overrides[get_embedder] = lambda: Broken()
    try:
        response = log(client, coord_headers, learner["id"])
        assert response.status_code == 201
        assert response.json()["alignments"] == [] and "not available" in response.json()["suggestions_error"]
    finally:
        app.dependency_overrides[get_embedder] = fake
    retry = client.post(f"/api/ilaw/{response.json()['id']}/suggest", headers=coord_headers).json()
    assert retry["alignments"] and retry["suggestions_error"] is None


# --- Permissions ------------------------------------------------------------------------------------


def test_ilaw_permissions(client, coord_headers, active, make_user, login):
    learner, _ = active()
    teacher = make_user(Role.TEACHER)
    client.post(f"/api/learners/{learner['id']}/assignments", headers=coord_headers, json={"user_id": teacher.id})
    assigned = login(teacher)
    entry = log(client, assigned, learner["id"])
    assert entry.status_code == 201
    link_id = entry.json()["alignments"][0]["id"]
    assert client.post(f"/api/ilaw-links/{link_id}/confirm", headers=assigned).status_code == 200

    head = login(make_user(Role.SCHOOL_HEAD))
    assert client.get(f"/api/learners/{learner['id']}/ilaw", headers=head).status_code == 200
    assert client.get(f"/api/ilaw/{entry.json()['id']}", headers=head).status_code == 200
    assert log(client, head, learner["id"], title="Head entry").status_code == 403
    assert client.post(f"/api/ilaw-links/{link_id}/reject", headers=head).status_code == 403
    assert client.delete(f"/api/ilaw/{entry.json()['id']}", headers=head).status_code == 403

    stranger = login(make_user(Role.TEACHER))
    assert client.get(f"/api/learners/{learner['id']}/ilaw", headers=stranger).status_code == 404
    assert client.get(f"/api/ilaw/{entry.json()['id']}", headers=stranger).status_code == 404
    assert client.post(f"/api/ilaw-links/{link_id}/reject", headers=stranger).status_code == 404
    assert client.get(f"/api/learners/{learner['id']}/ilaw").status_code == 401

    assert client.delete(f"/api/ilaw/{entry.json()['id']}", headers=assigned).status_code == 204
