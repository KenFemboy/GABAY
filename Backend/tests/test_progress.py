"""Stage 11: progress monitoring - validation, aim line/status, timeline, attention list."""

from datetime import date

import pytest

from app.models.user import Role
from app.services import progress_service
from app.services.progress_analysis import Point, aim_value, goal_status
from test_iep import complete, create, prepared  # noqa: F401
from test_ilaw import active, log  # noqa: F401
from test_matching import (  # noqa: F401
    FakeEmbedder,
    bank,
    coord_headers,
    coordinator,
    embedder,
    learner_with_needs,
)

TODAY = date(2026, 3, 1)  # inside the test IEP period (1 Jun 2025 - 31 May 2026)


class FrozenDate(date):
    @classmethod
    def today(cls):
        return TODAY


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    monkeypatch.setattr(progress_service, "date", FrozenDate)


def goal(iep, method):
    return next(g for g in iep["goals"] if g["measurement_method"] == method)


def add(client, headers, learner_id, **body):
    body.setdefault("evidence_type", "probe")
    body.setdefault("recorded_on", "2026-02-01")
    return client.post(f"/api/learners/{learner_id}/progress", headers=headers, json=body)


def fields(response):
    return {d["field"] for d in response.json()["error"].get("details", [])}


# --- Aim line and status (pure) ---------------------------------------------------------


def test_aim_value_and_clamping():
    start, end = date(2025, 6, 1), date(2026, 5, 31)
    assert aim_value(30, 80, start, end, start) == 30
    assert aim_value(30, 80, start, end, end) == 80
    assert aim_value(30, 80, start, end, date(2027, 1, 1)) == 80
    mid = aim_value(30, 80, start, end, date(2025, 11, 30))
    assert 54 < mid < 56
    assert aim_value(10, 2, start, end, date(2025, 11, 30)) < 10  # decreasing goal


@pytest.mark.parametrize(
    ("points", "baseline", "target", "expected"),
    [
        ([], 30, 80, "no_data"),
        ([(date(2026, 2, 20), 85)], 30, 80, "met"),
        ([(date(2026, 2, 10), 40), (date(2026, 2, 17), 45), (date(2026, 2, 24), 42)], 30, 80, "below_aim"),
        ([(date(2026, 2, 10), 65), (date(2026, 2, 17), 70), (date(2026, 2, 24), 72)], 30, 80, "on_track"),
        ([(date(2025, 12, 1), 70)], 30, 80, "no_recent_data"),
        ([(date(2026, 2, 20), 50)], None, 80, "no_baseline"),
        # Decreasing goal (fewer call-outs): high values are behind, reaching <= target is met.
        ([(date(2026, 2, 10), 9), (date(2026, 2, 17), 9), (date(2026, 2, 24), 8)], 10, 2, "below_aim"),
        ([(date(2026, 2, 10), 4), (date(2026, 2, 17), 3), (date(2026, 2, 24), 4)], 10, 2, "on_track"),
        ([(date(2026, 2, 24), 2)], 10, 2, "met"),
    ],
)
def test_goal_status(points, baseline, target, expected):
    result = goal_status(baseline=baseline, target=target, start=date(2025, 6, 1), end=date(2026, 5, 31),
                         points=[Point(d, v) for d, v in points], today=TODAY)
    assert result.status == expected


def test_status_uses_median_of_last_three_and_not_started():
    # One bad latest point alone does not flag the goal: median(70, 72, 20) = 70.
    pts = [Point(date(2026, 2, 10), 70), Point(date(2026, 2, 17), 72), Point(date(2026, 2, 24), 20)]
    result = goal_status(baseline=30, target=80, start=date(2025, 6, 1), end=date(2026, 5, 31), points=pts, today=TODAY)
    assert result.status == "on_track" and result.latest == 20
    fresh = goal_status(baseline=30, target=80, start=date(2026, 2, 20), end=date(2026, 5, 31), points=[], today=TODAY)
    assert fresh.status == "not_started"


# --- Validation against the goal's measurement type ----------------------------------------


def test_percent_validation_and_conversion(client, coord_headers, active):
    learner, iep = active()
    g = goal(iep, "percent_accuracy")
    lid = learner["id"]
    assert fields(add(client, coord_headers, lid, iep_goal_id=g["id"], value=120)) == {"value"}
    converted = add(client, coord_headers, lid, iep_goal_id=g["id"], correct=7, total=10)
    assert converted.status_code == 201 and converted.json()["value"] == 70 and converted.json()["unit"] == "percent"
    assert fields(add(client, coord_headers, lid, iep_goal_id=g["id"], value=50, unit="minutes")) == {"unit"}
    assert fields(add(client, coord_headers, lid, iep_goal_id=g["id"], correct=12, total=10)) == {"correct", "value"}


def test_trials_and_whole_number_rules(client, coord_headers, active):
    learner, iep = active()
    lid = learner["id"]
    trials = goal(iep, "trials")
    assert fields(add(client, coord_headers, lid, iep_goal_id=trials["id"], value=3)) == {"out_of"}
    assert fields(add(client, coord_headers, lid, iep_goal_id=trials["id"], value=6, out_of=5)) == {"value"}
    ok = add(client, coord_headers, lid, iep_goal_id=trials["id"], value=3, out_of=5)
    assert ok.status_code == 201 and ok.json()["unit"] == "trials" and ok.json()["out_of"] == 5
    freq = goal(iep, "frequency")
    assert fields(add(client, coord_headers, lid, iep_goal_id=freq["id"], value=2.5)) == {"value"}
    assert add(client, coord_headers, lid, iep_goal_id=freq["id"], value=3).status_code == 201


def test_evidence_type_rules(client, coord_headers, active):
    learner, iep = active()
    lid = learner["id"]
    g = goal(iep, "percent_accuracy")
    assert fields(add(client, coord_headers, lid, value=50)) == {"iep_goal_id"}  # probe needs a goal
    assert fields(add(client, coord_headers, lid, evidence_type="test", iep_goal_id=g["id"])) == {"value"}
    assert fields(add(client, coord_headers, lid, evidence_type="observation")) == {"note"}
    obs = add(client, coord_headers, lid, evidence_type="observation", note="Used counters without prompting.")
    assert obs.status_code == 201 and obs.json()["value"] is None
    assert fields(add(client, coord_headers, lid, evidence_type="grade", value=85)) == {"subject", "grading_period"}
    assert fields(add(client, coord_headers, lid, evidence_type="grade", subject="Math", grading_period="Q2", value=120)) == {"value"}
    grade = add(client, coord_headers, lid, evidence_type="grade", subject="Mathematics", grading_period="Q2",
                value=82, iep_goal_id=g["id"])
    assert grade.status_code == 201 and grade.json()["unit"] == "grade"
    assert fields(add(client, coord_headers, lid, iep_goal_id=g["id"], value=50, recorded_on="2026-04-01")) == {"recorded_on"}
    assert fields(add(client, coord_headers, lid, iep_goal_id=g["id"], value=50, recorded_on="2025-01-01")) == {"recorded_on"}
    assert fields(add(client, coord_headers, lid, iep_goal_id=999999, value=50)) == {"iep_goal_id"}


def test_requires_active_iep(client, coord_headers, prepared):
    learner, _, _ = prepared(code="NOPROG")
    response = add(client, coord_headers, learner["id"], evidence_type="observation", note="x")
    assert response.status_code == 409 and response.json()["error"]["code"] == "no_active_iep"
    assert client.get(f"/api/learners/{learner['id']}/progress/goals", headers=coord_headers).json() == {
        "iep_id": None, "iep_version": None, "goals": []}


# --- Goal progress, timeline, attention ----------------------------------------------------------


def test_goal_progress_chart_data(client, coord_headers, active):
    learner, iep = active()
    g = goal(iep, "percent_accuracy")
    lid = learner["id"]
    for day, value in (("2026-02-20", 40), ("2026-01-10", 35), ("2026-02-27", 42)):
        add(client, coord_headers, lid, iep_goal_id=g["id"], value=value, recorded_on=day)
    add(client, coord_headers, lid, evidence_type="grade", subject="Math", grading_period="Q3", value=80, iep_goal_id=g["id"])

    data = client.get(f"/api/iep-goals/{g['id']}/progress", headers=coord_headers).json()
    assert [p["recorded_on"] for p in data["points"]] == ["2026-01-10", "2026-02-20", "2026-02-27"]
    assert [o["evidence_type"] for o in data["other"]] == ["grade"]  # grades are not plotted
    assert data["aim_start"] == {"date": g["start_date"], "value": 30.0}
    assert data["aim_end"] == {"date": g["target_date"], "value": g["target_value"]}
    assert data["status"]["status"] == "below_aim" and data["status"]["latest"] == 42
    assert data["status"]["expected"] > 42 and data["goal"]["number"] >= 1

    all_goals = client.get(f"/api/learners/{lid}/progress/goals", headers=coord_headers).json()
    assert all_goals["iep_id"] == iep["id"] and len(all_goals["goals"]) == len(iep["goals"])


def test_timeline_merges_ilaw_and_records(client, coord_headers, active):
    learner, iep = active()
    lid = learner["id"]
    g = goal(iep, "percent_accuracy")
    log(client, coord_headers, lid, activity_date="2026-02-10")
    add(client, coord_headers, lid, iep_goal_id=g["id"], value=55, recorded_on="2026-02-12")
    add(client, coord_headers, lid, evidence_type="grade", subject="Mathematics", grading_period="Q3", value=81, recorded_on="2026-02-15")
    add(client, coord_headers, lid, evidence_type="observation", note="Calm during transitions.", recorded_on="2026-02-11")

    items = client.get(f"/api/learners/{lid}/timeline", headers=coord_headers).json()["items"]
    assert [i["kind"] for i in items] == ["grade", "probe", "observation", "ilaw"]
    assert items[-1]["title"].startswith("Subtraction")
    only = client.get(f"/api/learners/{lid}/timeline", headers=coord_headers, params={"types": "grade,ilaw"}).json()["items"]
    assert [i["kind"] for i in only] == ["grade", "ilaw"]
    ranged = client.get(f"/api/learners/{lid}/timeline", headers=coord_headers,
                        params={"from": "2026-02-11", "to": "2026-02-12"}).json()["items"]
    assert {i["kind"] for i in ranged} == {"probe", "observation"}

    summary = client.get(f"/api/learners/{lid}/summary", headers=coord_headers).json()["modules"]["progress"]
    assert summary["available"] is True and summary["count"] == 3


def test_attention_list_respects_visibility(client, coord_headers, active, make_user, login):
    learner, iep = active(code="ATT-1")
    g = goal(iep, "percent_accuracy")
    for day, value in (("2026-02-10", 35), ("2026-02-17", 36), ("2026-02-24", 34)):
        add(client, coord_headers, learner["id"], iep_goal_id=g["id"], value=value, recorded_on=day)

    rows = client.get("/api/progress/attention", headers=coord_headers).json()["items"]
    mine = [r for r in rows if r["learner_id"] == learner["id"]]
    assert mine and mine[0]["progress"]["status"]["status"] == "below_aim"
    assert mine[0]["progress"]["goal"]["id"] == g["id"]
    assert {r["progress"]["status"]["status"] for r in rows} <= {"below_aim", "no_recent_data", "no_data", "no_baseline"}
    only_below = client.get("/api/progress/attention", headers=coord_headers, params={"status": "below_aim"}).json()["items"]
    assert only_below and all(r["progress"]["status"]["status"] == "below_aim" for r in only_below)

    head = login(make_user(Role.SCHOOL_HEAD))
    assert any(r["learner_id"] == learner["id"] for r in client.get("/api/progress/attention", headers=head).json()["items"])
    stranger = login(make_user(Role.TEACHER))
    assert client.get("/api/progress/attention", headers=stranger).json()["items"] == []
    teacher = make_user(Role.TEACHER)
    client.post(f"/api/learners/{learner['id']}/assignments", headers=coord_headers, json={"user_id": teacher.id})
    assert any(r["learner_id"] == learner["id"] for r in client.get("/api/progress/attention", headers=login(teacher)).json()["items"])


def test_update_and_delete(client, coord_headers, active):
    learner, iep = active()
    g = goal(iep, "percent_accuracy")
    rec = add(client, coord_headers, learner["id"], iep_goal_id=g["id"], value=50).json()
    updated = client.patch(f"/api/progress/{rec['id']}", headers=coord_headers, json={"correct": 9, "total": 10})
    assert updated.status_code == 200 and updated.json()["value"] == 90
    bad = client.patch(f"/api/progress/{rec['id']}", headers=coord_headers, json={"value": 101})
    assert bad.status_code == 422
    assert client.delete(f"/api/progress/{rec['id']}", headers=coord_headers).status_code == 204


def test_progress_permissions(client, coord_headers, active, make_user, login):
    learner, iep = active()
    g = goal(iep, "percent_accuracy")
    teacher = make_user(Role.TEACHER)
    client.post(f"/api/learners/{learner['id']}/assignments", headers=coord_headers, json={"user_id": teacher.id})
    assigned = login(teacher)
    rec = add(client, assigned, learner["id"], iep_goal_id=g["id"], value=60)
    assert rec.status_code == 201

    head = login(make_user(Role.SCHOOL_HEAD))
    assert client.get(f"/api/learners/{learner['id']}/progress/goals", headers=head).status_code == 200
    assert client.get(f"/api/learners/{learner['id']}/timeline", headers=head).status_code == 200
    assert add(client, head, learner["id"], iep_goal_id=g["id"], value=60).status_code == 403
    assert client.delete(f"/api/progress/{rec.json()['id']}", headers=head).status_code == 403

    stranger = login(make_user(Role.TEACHER))
    assert client.get(f"/api/learners/{learner['id']}/progress/goals", headers=stranger).status_code == 404
    assert client.get(f"/api/iep-goals/{g['id']}/progress", headers=stranger).status_code == 404
    assert client.patch(f"/api/progress/{rec.json()['id']}", headers=stranger, json={"value": 1}).status_code == 404
    assert client.get("/api/progress/attention").status_code == 401
