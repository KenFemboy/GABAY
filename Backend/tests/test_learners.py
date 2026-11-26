"""Learner records: validation, uniqueness, role and row-level access.

All learner data here is synthetic.
"""

from datetime import date, timedelta

import pytest

from app.models.user import Role

MODULES = ["assessments", "iep", "ilaw", "progress", "evaluations"]


def learner_payload(**overrides):
    payload = {
        "learner_code": "TEST-001",
        "first_name": "Sample",
        "last_name": "Learner",
        "birth_date": "2016-06-15",
        "sex": "female",
        "grade_level": "3",
        "section": "Sampaguita",
        "school_year": "2025-2026",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def coordinator_headers(make_user, login):
    return login(make_user(Role.SNED_COORDINATOR))


@pytest.fixture
def create_learner(client, coordinator_headers):
    def _create(**overrides):
        response = client.post(
            "/api/learners", headers=coordinator_headers, json=learner_payload(**overrides)
        )
        assert response.status_code == 201, response.text
        return response.json()

    return _create


def error_fields(response):
    return {d["field"]: d["message"] for d in response.json()["error"].get("details", [])}


# --- Validation --------------------------------------------------------------


def test_missing_required_fields_are_rejected_with_messages(client, coordinator_headers):
    response = client.post("/api/learners", headers=coordinator_headers, json={})
    assert response.status_code == 422
    fields = error_fields(response)
    for field in [
        "learner_code",
        "first_name",
        "last_name",
        "birth_date",
        "sex",
        "grade_level",
        "section",
        "school_year",
    ]:
        assert fields[field] == "This field is required."
    assert "middle_name" not in fields


def test_blank_strings_are_rejected(client, coordinator_headers):
    response = client.post(
        "/api/learners",
        headers=coordinator_headers,
        json=learner_payload(first_name="   ", section=""),
    )
    assert response.status_code == 422
    fields = error_fields(response)
    assert fields["first_name"] == "This field is required."
    assert fields["section"] == "This field is required."


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("school_year", "2025", "Use the format 2025-2026."),
        ("school_year", "2025-2027", "Use the format 2025-2026."),
        ("learner_code", "bad code!", "Learner code may contain only letters"),
        ("birth_date", str(date.today() + timedelta(days=1)), "cannot be in the future"),
        ("grade_level", "13", "Input should be"),
    ],
)
def test_invalid_values_are_rejected(client, coordinator_headers, field, value, expected):
    response = client.post(
        "/api/learners", headers=coordinator_headers, json=learner_payload(**{field: value})
    )
    assert response.status_code == 422
    assert expected in error_fields(response)[field]


def test_patch_cannot_null_required_fields(client, coordinator_headers, create_learner):
    learner = create_learner()
    response = client.patch(
        f"/api/learners/{learner['id']}", headers=coordinator_headers, json={"first_name": None}
    )
    assert response.status_code == 422
    assert error_fields(response)["first_name"] == "This field is required."


# --- Uniqueness --------------------------------------------------------------


def test_duplicate_learner_code_is_rejected_case_insensitively(
    client, coordinator_headers, create_learner
):
    create_learner(learner_code="ABC-1")
    response = client.post(
        "/api/learners", headers=coordinator_headers, json=learner_payload(learner_code=" abc-1 ")
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "learner_code_taken"


def test_patch_to_existing_code_is_rejected(client, coordinator_headers, create_learner):
    create_learner(learner_code="ABC-1")
    other = create_learner(learner_code="ABC-2")
    response = client.patch(
        f"/api/learners/{other['id']}", headers=coordinator_headers, json={"learner_code": "abc-1"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "learner_code_taken"


# --- Coordinator CRUD, search and filters ------------------------------------


def test_coordinator_can_create_read_update_and_change_status(
    client, coordinator_headers, create_learner
):
    learner = create_learner(learner_code="  new-01 ", middle_name="  ")
    assert learner["learner_code"] == "NEW-01"
    assert learner["middle_name"] is None
    assert learner["status"] == "active"
    assert learner["full_name"] == "Sample Learner"

    fetched = client.get(f"/api/learners/{learner['id']}", headers=coordinator_headers)
    assert fetched.status_code == 200
    assert fetched.json()["learner_code"] == "NEW-01"

    updated = client.patch(
        f"/api/learners/{learner['id']}",
        headers=coordinator_headers,
        json={"middle_name": "Reyes", "status": "transferred", "grade_level": "4"},
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["status"] == "transferred"
    assert body["grade_level"] == "4"
    assert body["full_name"] == "Sample Reyes Learner"


def test_there_is_no_delete_endpoint(client, coordinator_headers, create_learner):
    learner = create_learner()
    response = client.delete(f"/api/learners/{learner['id']}", headers=coordinator_headers)
    assert response.status_code == 405


def test_list_search_filters_and_pagination(client, coordinator_headers, create_learner):
    create_learner(learner_code="A-1", first_name="Juan", last_name="Cruz", grade_level="1")
    create_learner(learner_code="A-2", first_name="Maria", last_name="Santos", section="Rosal")
    create_learner(
        learner_code="A-3", first_name="Jose", last_name="Reyes", school_year="2024-2025"
    )
    create_learner(learner_code="A-4", first_name="Ana", last_name="Lopez", status="graduated")

    def ids(**params):
        response = client.get("/api/learners", headers=coordinator_headers, params=params)
        assert response.status_code == 200, response.text
        return response.json()

    assert ids()["total"] == 4
    assert [x["learner_code"] for x in ids(search="juan cruz")["items"]] == ["A-1"]
    assert [x["learner_code"] for x in ids(search="a-2")["items"]] == ["A-2"]
    assert [x["learner_code"] for x in ids(grade_level="1")["items"]] == ["A-1"]
    assert [x["learner_code"] for x in ids(section="rosal")["items"]] == ["A-2"]
    assert [x["learner_code"] for x in ids(school_year="2024-2025")["items"]] == ["A-3"]
    assert [x["learner_code"] for x in ids(status="graduated")["items"]] == ["A-4"]

    page = ids(limit=2, offset=2)
    assert page["total"] == 4
    assert len(page["items"]) == 2
    # Ordered by last name: Cruz, Lopez, Reyes, Santos.
    assert [x["last_name"] for x in page["items"]] == ["Reyes", "Santos"]


def test_missing_learner_returns_404(client, coordinator_headers):
    response = client.get("/api/learners/99999", headers=coordinator_headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


# --- Role access -------------------------------------------------------------


def test_school_head_can_read_but_not_write(client, make_user, login, create_learner):
    learner = create_learner()
    headers = login(make_user(Role.SCHOOL_HEAD))

    assert client.get("/api/learners", headers=headers).json()["total"] == 1
    assert client.get(f"/api/learners/{learner['id']}", headers=headers).status_code == 200
    assert client.get(f"/api/learners/{learner['id']}/summary", headers=headers).status_code == 200

    create = client.post("/api/learners", headers=headers, json=learner_payload(learner_code="X"))
    assert create.status_code == 403
    patch = client.patch(f"/api/learners/{learner['id']}", headers=headers, json={"section": "B"})
    assert patch.status_code == 403


def test_system_admin_has_no_learner_access(client, make_user, login, create_learner):
    learner = create_learner()
    headers = login(make_user(Role.SYSTEM_ADMIN))
    assert client.get("/api/learners", headers=headers).status_code == 403
    assert client.get(f"/api/learners/{learner['id']}", headers=headers).status_code == 403


def test_learner_endpoints_require_authentication(client):
    assert client.get("/api/learners").status_code == 401
    assert client.get("/api/learners/1").status_code == 401


def test_teacher_sees_only_assigned_learners_for_current_school_year(
    client, make_user, login, coordinator_headers, create_learner
):
    teacher = make_user(Role.TEACHER)
    headers = login(teacher)
    mine = create_learner(learner_code="MINE")
    other = create_learner(learner_code="OTHER")

    # Not assigned yet: empty list, and records look like they do not exist.
    assert client.get("/api/learners", headers=headers).json()["total"] == 0
    for path in ["", "/summary", "/assignments"]:
        response = client.get(f"/api/learners/{mine['id']}{path}", headers=headers)
        assert response.status_code == 404, path

    assigned = client.post(
        f"/api/learners/{mine['id']}/assignments",
        headers=coordinator_headers,
        json={"user_id": teacher.id},
    )
    assert assigned.status_code == 201, assigned.text
    assert assigned.json()["school_year"] == "2025-2026"
    assert assigned.json()["user_name"] == teacher.name

    listing = client.get("/api/learners", headers=headers).json()
    assert [x["id"] for x in listing["items"]] == [mine["id"]]
    assert client.get(f"/api/learners/{mine['id']}", headers=headers).status_code == 200
    assert client.get(f"/api/learners/{other['id']}", headers=headers).status_code == 404

    # Teachers are read-only.
    patch = client.patch(f"/api/learners/{mine['id']}", headers=headers, json={"section": "B"})
    assert patch.status_code == 403

    # Moving the learner to a new school year ends the old assignment's access.
    client.patch(
        f"/api/learners/{mine['id']}", headers=coordinator_headers, json={"school_year": "2026-2027"}
    )
    assert client.get(f"/api/learners/{mine['id']}", headers=headers).status_code == 404


# --- Summary -----------------------------------------------------------------


def test_summary_lists_every_module(client, coordinator_headers, create_learner):
    learner = create_learner()
    response = client.get(f"/api/learners/{learner['id']}/summary", headers=coordinator_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["learner"]["id"] == learner["id"]
    assert list(body["modules"]) == MODULES
    # Stage 4 built assessments and Stage 9 the IEP; the rest arrive in later stages.
    built = {"assessments", "iep"}
    for name, module in body["modules"].items():
        expected_available = name in built
        assert module == {
            "available": expected_available, "count": 0, "latest_status": None, "latest_at": None
        }


# --- Assignments -------------------------------------------------------------


def test_assignment_rules(client, make_user, coordinator_headers, create_learner):
    learner = create_learner()
    teacher = make_user(Role.TEACHER)
    head = make_user(Role.SCHOOL_HEAD)
    base = f"/api/learners/{learner['id']}/assignments"

    not_teacher = client.post(base, headers=coordinator_headers, json={"user_id": head.id})
    assert not_teacher.status_code == 400
    assert not_teacher.json()["error"]["code"] == "invalid_assignee"

    first = client.post(base, headers=coordinator_headers, json={"user_id": teacher.id})
    assert first.status_code == 201
    duplicate = client.post(base, headers=coordinator_headers, json={"user_id": teacher.id})
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "already_assigned"

    listing = client.get(base, headers=coordinator_headers).json()
    assert [a["user_id"] for a in listing] == [teacher.id]

    removed = client.delete(f"{base}/{first.json()['id']}", headers=coordinator_headers)
    assert removed.status_code == 204
    assert client.get(base, headers=coordinator_headers).json() == []
    again = client.delete(f"{base}/{first.json()['id']}", headers=coordinator_headers)
    assert again.status_code == 404


def test_teacher_picker_lists_only_active_teachers(client, make_user, login):
    from app.models.user import UserStatus

    active = make_user(Role.TEACHER)
    make_user(Role.TEACHER, status=UserStatus.INACTIVE)
    make_user(Role.SCHOOL_HEAD)
    coordinator = make_user(Role.SNED_COORDINATOR)

    response = client.get("/api/users/teachers", headers=login(coordinator))
    assert response.status_code == 200
    assert response.json() == [{"id": active.id, "name": active.name}]

    teacher_headers = login(active)
    assert client.get("/api/users/teachers", headers=teacher_headers).status_code == 403
