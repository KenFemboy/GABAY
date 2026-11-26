"""Stage 8: semantic goal matching. Synthetic data; SQLite path (numpy search)."""

import hashlib
import json
import os
import re
from datetime import date

import numpy as np
import pytest
from sqlalchemy import func, select

from app.db.vector import EMBEDDING_DIMS, EmbeddingVector
from app.main import app
from app.models.assessment import Assessment
from app.models.extraction import ExtractionFinding, ExtractionVersion
from app.models.goal import GoalUsage
from app.models.matching import NeedEmbedding
from app.models.user import Role
from app.scripts import benchmark_matching
from app.scripts.seed_goal_bank import load_seed, seed
from app.services import embedding_service, goal_service, matching_service
from app.services.embedding_service import get_embedder, vector_search


class FakeEmbedder:
    """Bag-of-words hashing into 384 dims: shared words -> similar vectors."""

    model = "fake-bow-384"

    def __init__(self):
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        out = np.zeros((len(texts), EMBEDDING_DIMS), dtype=np.float32)
        for i, text in enumerate(texts):
            for word in re.findall(r"[a-z]+", text.lower()):
                if len(word) > 3:
                    out[i, int(hashlib.md5(word.encode()).hexdigest(), 16) % EMBEDDING_DIMS] += 1
        return embedding_service._normalize(out)


@pytest.fixture
def embedder(client):
    fake = FakeEmbedder()
    app.dependency_overrides[get_embedder] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_embedder, None)


@pytest.fixture
def coordinator(make_user):
    return make_user(Role.SNED_COORDINATOR)


@pytest.fixture
def coord_headers(login, coordinator):
    return login(coordinator)


@pytest.fixture
def bank(db_session):
    """Starter goal bank with every goal active."""
    seed(db_session, load_seed())
    for goal in db_session.scalars(select(goal_service.Goal)):
        goal.status = "active"
    db_session.commit()
    return {g.code: g for g in db_session.scalars(select(goal_service.Goal))}


@pytest.fixture
def learner_with_needs(client, coord_headers, coordinator, db_session):
    """A Grade 3 learner with one APPROVED extraction version (+ a draft that must be ignored)."""

    def _make(needs=None, grade="3", extra_categories=True, code="MT-1"):
        learner = client.post(
            "/api/learners",
            headers=coord_headers,
            json={"learner_code": code, "first_name": "Sample", "last_name": "Match", "birth_date": "2016-01-01",
                  "sex": "female", "grade_level": grade, "section": "Rosal", "school_year": "2025-2026"},
        ).json()
        assessment = Assessment(
            learner_id=learner["id"], assessment_type="informal", assessment_date=date(2025, 8, 1),
            assessor="Adviser", processing_status="finalized", created_by=coordinator.id,
        )
        db_session.add(assessment)
        db_session.flush()
        approved = ExtractionVersion(
            assessment_id=assessment.id, version_number=1, method="rule", status="approved",
            source_text_hash="x" * 64, extractor_version="rules-1", created_by=coordinator.id,
        )
        draft = ExtractionVersion(
            assessment_id=assessment.id, version_number=2, method="rule", status="draft",
            source_text_hash="x" * 64, extractor_version="rules-1", created_by=coordinator.id,
        )
        needs = needs or [
            ("mathematics", "Has difficulty with subtraction and word problems."),
            ("motor", "Holds a pencil with a fist grip."),
        ]
        for pos, (domain, text) in enumerate(needs):
            approved.findings.append(ExtractionFinding(category="need", domain=domain, text=text, position=pos, origin="extracted"))
        if extra_categories:
            approved.findings.append(ExtractionFinding(category="strength", domain="reading", text="Recognizes all letters.", position=90, origin="extracted"))
            approved.findings.append(ExtractionFinding(category="recommendation", domain="reading", text="Daily phonics practice.", position=91, origin="extracted"))
        draft.findings.append(ExtractionFinding(category="need", domain="reading", text="Draft need that must be ignored.", position=0, origin="extracted"))
        db_session.add_all([approved, draft])
        db_session.commit()
        return learner

    return _make


def run(client, headers, learner_id, **options):
    return client.post(f"/api/learners/{learner_id}/matching-runs", headers=headers, json=options)


# --- Vector column type ----------------------------------------------------------


def test_embedding_vector_roundtrip_and_dims(db_session):
    column = EmbeddingVector(EMBEDDING_DIMS)
    vec = np.arange(EMBEDDING_DIMS, dtype=np.float32)
    dialect = db_session.get_bind().dialect
    stored = column.process_bind_param(vec, dialect)
    assert isinstance(stored, bytes)
    assert np.array_equal(column.process_result_value(stored, dialect), vec)
    with pytest.raises(ValueError):
        column.process_bind_param(np.zeros(10), dialect)


def test_wrong_model_dimensions_are_refused():
    with pytest.raises(embedding_service.EmbeddingUnavailable):
        embedding_service.check_dims(np.zeros((2, 64), dtype=np.float32))


# --- vector_search filters -------------------------------------------------------


def test_vector_search_filters_threshold_and_order(db_session, bank):
    fake = FakeEmbedder()
    embedding_service.reindex(db_session, fake)
    query = fake.embed(["Mathematics – difficulty with subtraction word problems"])[0]

    hits = vector_search(db_session, query, model=fake.model, k=5)
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True) and len(hits) == 5

    math_only = vector_search(db_session, query, model=fake.model, k=50, domain_code="mathematics")
    assert {h.version.domain.code for h in math_only} == {"mathematics"}

    k3 = vector_search(db_session, query, model=fake.model, k=50, grade_band="K-3")
    assert {h.version.grade_band for h in k3} <= {"K-3", "any"}
    assert "MA-005" not in [h.goal.code for h in k3]  # a 4-6 goal

    cut = vector_search(db_session, query, model=fake.model, k=50, min_score=0.3)
    assert all(h.score >= 0.3 for h in cut)
    assert len(cut) < len(vector_search(db_session, query, model=fake.model, k=50))

    # Archived goals disappear immediately, even before reindex.
    top = hits[0].goal
    top.status = "archived"
    db_session.commit()
    assert top.code not in [h.goal.code for h in vector_search(db_session, query, model=fake.model, k=50)]


# --- Running matching --------------------------------------------------------------


def test_run_matching_uses_only_approved_needs(client, coord_headers, bank, learner_with_needs, embedder, db_session):
    learner = learner_with_needs()
    response = run(client, coord_headers, learner["id"])
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["model"] == "fake-bow-384"
    assert data["model_version"] == "fake-bow-384|text-v1"
    assert data["top_k"] == 5 and data["min_score"] == 0.35 and data["same_domain"] is True
    assert data["grade_band"] == "K-3" and data["need_count"] == 2
    assert [n["text"] for n in data["needs"]] == [
        "Has difficulty with subtraction and word problems.", "Holds a pencil with a fist grip."
    ]
    math = data["needs"][0]["suggestions"]
    assert math, "expected suggestions for the math need"
    assert [s["rank"] for s in math] == list(range(1, len(math) + 1))
    assert all(s["score"] >= 0.35 and s["model_version"] == data["model_version"] for s in math)
    assert all(s["goal_version"]["domain"]["code"] == "mathematics" for s in math)
    # The fake bag-of-words embedder is crude; the real model is measured by the benchmark.
    assert {s["goal_code"] for s in math} & {"MA-004", "MA-006"}
    assert all(s["status"] == "suggested" and s["source"] == "matched" for s in math)

    # One vector per need; a second run reuses them.
    assert db_session.scalar(select(func.count(NeedEmbedding.id))) == 2
    calls = embedder.calls
    run(client, coord_headers, learner["id"])
    assert db_session.scalar(select(func.count(NeedEmbedding.id))) == 2
    assert embedder.calls == calls  # nothing new to embed


def test_run_options(client, coord_headers, bank, learner_with_needs, embedder):
    learner = learner_with_needs()
    data = run(client, coord_headers, learner["id"], top_k=2, min_score=0, same_domain=False, use_grade_band=False).json()
    assert data["grade_band"] is None and data["same_domain"] is False
    assert all(len(n["suggestions"]) == 2 for n in data["needs"])
    strict = run(client, coord_headers, learner["id"], min_score=0.99).json()
    assert all(n["suggestions"] == [] for n in strict["needs"])
    assert run(client, coord_headers, learner["id"], top_k=50).status_code == 422


def test_no_approved_needs(client, coord_headers, bank, embedder):
    learner = client.post(
        "/api/learners", headers=coord_headers,
        json={"learner_code": "NO-1", "first_name": "A", "last_name": "B", "birth_date": "2016-01-01",
              "sex": "male", "grade_level": "2", "section": "Rosal", "school_year": "2025-2026"},
    ).json()
    response = run(client, coord_headers, learner["id"])
    assert response.status_code == 409 and response.json()["error"]["code"] == "no_approved_needs"


# --- Decisions ------------------------------------------------------------------------


def latest(client, headers, learner_id):
    return client.get(f"/api/learners/{learner_id}/recommendations/latest", headers=headers).json()


def test_accept_edit_reject_reset(client, coord_headers, bank, learner_with_needs, embedder, db_session):
    learner = learner_with_needs()
    data = run(client, coord_headers, learner["id"], min_score=0).json()
    first, second = data["needs"][0]["suggestions"][:2]

    accepted = client.post(f"/api/recommendations/{first['id']}/accept", headers=coord_headers, json={}).json()
    assert accepted["status"] == "accepted" and accepted["decided_by_name"]
    assert accepted["final_statement"] == first["goal_version"]["statement"]
    # Accepting locks the goal version (Stage 7): a later bank edit makes a new version.
    assert db_session.scalar(select(func.count(GoalUsage.id)).where(GoalUsage.goal_version_id == first["goal_version"]["id"])) == 1

    edited = client.patch(
        f"/api/recommendations/{first['id']}", headers=coord_headers,
        json={"edited_statement": "Given counters, the learner will solve 10 subtraction facts within 10 with 70% accuracy.",
              "edited_target_value": 70},
    ).json()
    assert edited["edited_target_value"] == 70 and edited["final_target_value"] == 70
    assert edited["final_statement"].startswith("Given counters")
    db_session.expire_all()
    goal = db_session.get(goal_service.Goal, first["goal_id"])
    assert goal.current_version.target_value != 70 or goal.current_version.statement != edited["final_statement"]

    rejected = client.post(f"/api/recommendations/{second['id']}/reject", headers=coord_headers, json={"reason": "Too easy"}).json()
    assert rejected["status"] == "rejected" and rejected["reject_reason"] == "Too easy"
    undone = client.post(f"/api/recommendations/{second['id']}/reset", headers=coord_headers).json()
    assert undone["status"] == "suggested" and undone["reject_reason"] is None

    # Editing something that is not accepted is refused.
    assert client.patch(f"/api/recommendations/{second['id']}", headers=coord_headers,
                        json={"edited_target_value": 1}).status_code == 409

    selected = latest(client, coord_headers, learner["id"])["selected"]
    assert [s["id"] for s in selected] == [first["id"]]


def test_edits_identical_to_bank_are_not_stored(client, coord_headers, bank, learner_with_needs, embedder):
    learner = learner_with_needs()
    rec = run(client, coord_headers, learner["id"], min_score=0).json()["needs"][0]["suggestions"][0]
    same = client.post(f"/api/recommendations/{rec['id']}/accept", headers=coord_headers,
                       json={"edited_statement": rec["goal_version"]["statement"]}).json()
    assert same["edited_statement"] is None


def test_rerun_carries_decisions_and_selected_goals(client, coord_headers, bank, learner_with_needs, embedder):
    learner = learner_with_needs()
    first_run = run(client, coord_headers, learner["id"], min_score=0).json()
    a, b = first_run["needs"][0]["suggestions"][:2]
    client.post(f"/api/recommendations/{a['id']}/accept", headers=coord_headers, json={"edited_target_value": 60})
    client.post(f"/api/recommendations/{b['id']}/reject", headers=coord_headers, json={"reason": "No"})

    second_run = run(client, coord_headers, learner["id"], min_score=0).json()
    by_version = {s["goal_version"]["id"]: s for s in second_run["needs"][0]["suggestions"]}
    assert by_version[a["goal_version"]["id"]]["status"] == "accepted"
    assert by_version[a["goal_version"]["id"]]["edited_target_value"] == 60
    assert by_version[b["goal_version"]["id"]]["status"] == "rejected"

    view = latest(client, coord_headers, learner["id"])
    assert view["run"]["id"] == second_run["id"]
    assert len(view["selected"]) == 1 and view["selected"][0]["goal_version"]["id"] == a["goal_version"]["id"]
    runs = client.get(f"/api/learners/{learner['id']}/matching-runs", headers=coord_headers).json()["items"]
    assert [r["id"] for r in runs] == [second_run["id"], first_run["id"]]


def test_manual_add_and_remove(client, coord_headers, bank, learner_with_needs, embedder, db_session):
    learner = learner_with_needs()
    data = run(client, coord_headers, learner["id"]).json()
    need_id = data["needs"][0]["id"]
    goal = bank["MA-007"]

    added = client.post(
        f"/api/learners/{learner['id']}/recommendations", headers=coord_headers,
        json={"goal_id": goal.id, "finding_id": need_id, "edited_criterion": "across 4 sessions"},
    )
    assert added.status_code == 201, added.text
    rec = added.json()
    assert rec["source"] == "manual" and rec["status"] == "accepted" and rec["score"] is None and rec["rank"] is None
    assert rec["final_criterion"] == "across 4 sessions"
    assert rec["id"] in [s["id"] for s in latest(client, coord_headers, learner["id"])["selected"]]

    again = client.post(f"/api/learners/{learner['id']}/recommendations", headers=coord_headers, json={"goal_id": goal.id})
    assert again.status_code == 409

    # Invalid goal / finding.
    goal_b = bank["MA-008"]
    goal_b.status = "archived"
    db_session.commit()
    assert client.post(f"/api/learners/{learner['id']}/recommendations", headers=coord_headers,
                       json={"goal_id": goal_b.id}).status_code == 422
    draft_need = db_session.scalar(select(ExtractionFinding).where(ExtractionFinding.text.like("Draft need%")))
    assert client.post(f"/api/learners/{learner['id']}/recommendations", headers=coord_headers,
                       json={"goal_id": bank["MA-001"].id, "finding_id": draft_need.id}).status_code == 422

    assert client.post(f"/api/recommendations/{rec['id']}/reject", headers=coord_headers, json={}).status_code == 409
    assert client.delete(f"/api/recommendations/{rec['id']}", headers=coord_headers).status_code == 204
    matched = data["needs"][0]["suggestions"][0]
    assert client.delete(f"/api/recommendations/{matched['id']}", headers=coord_headers).status_code == 409


def test_matching_permissions(client, coord_headers, bank, learner_with_needs, embedder, make_user, login):
    learner = learner_with_needs()
    rec = run(client, coord_headers, learner["id"], min_score=0).json()["needs"][0]["suggestions"][0]

    teacher = make_user(Role.TEACHER)
    client.post(f"/api/learners/{learner['id']}/assignments", headers=coord_headers, json={"user_id": teacher.id})
    assigned = login(teacher)
    assert run(client, assigned, learner["id"]).status_code == 201
    assert client.post(f"/api/recommendations/{rec['id']}/accept", headers=assigned, json={}).status_code == 200

    head = login(make_user(Role.SCHOOL_HEAD))
    assert client.get(f"/api/learners/{learner['id']}/recommendations/latest", headers=head).status_code == 200
    assert client.get(f"/api/learners/{learner['id']}/selected-goals", headers=head).status_code == 200
    assert run(client, head, learner["id"]).status_code == 403
    assert client.post(f"/api/recommendations/{rec['id']}/reject", headers=head, json={}).status_code == 403

    stranger = login(make_user(Role.TEACHER))
    assert client.get(f"/api/learners/{learner['id']}/recommendations/latest", headers=stranger).status_code == 404
    assert client.post(f"/api/recommendations/{rec['id']}/reject", headers=stranger, json={}).status_code == 404
    assert run(client, stranger, learner["id"]).status_code == 404
    assert client.get(f"/api/learners/{learner['id']}/selected-goals").status_code == 401


# --- Benchmark ------------------------------------------------------------------------


def test_benchmark_file_is_valid():
    items = benchmark_matching.load_items()
    codes = {g["code"] for g in load_seed()["goals"]}
    domains = {d["code"] for d in load_seed()["domains"]}
    assert len(items) >= 60
    assert len({i["id"] for i in items}) == len(items)
    assert {i["lang"] for i in items} == {"en", "fil", "ocr"}
    for item in items:
        assert item["domain"] in domains and item["expected"], item["id"]
        assert set(item["expected"]) <= codes, item["id"]


def test_benchmark_metrics_with_fake_embedder():
    items = [
        {"id": "a", "lang": "en", "domain": "mathematics", "grade_band": "K-3",
         "text": "solve single-digit subtraction problems counters", "expected": ["MA-004"]},
        {"id": "b", "lang": "en", "domain": "motor", "grade_band": "K-3",
         "text": "zzzz qqqq", "expected": ["MO-004"]},
    ]
    text, results = benchmark_matching.run("fake", "", items=items, embedder=FakeEmbedder())
    main = results[0]
    assert main.n == 2 and main.hits[1] >= 1 and main.acc(5) >= 0.5
    assert 0 < main.random_top5 <= 1
    assert "Top-5" in text and "Random-ranking" in text


# --- Optional: real PostgreSQL + pgvector -----------------------------------------------


@pytest.mark.skipif(not os.environ.get("TEST_PG_URL"), reason="set TEST_PG_URL to a throwaway PostgreSQL+pgvector database")
def test_pgvector_search_matches_numpy():
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    import app.models  # noqa: F401
    from app.db.base import Base

    engine = create_engine(os.environ["TEST_PG_URL"])
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    pg = sessionmaker(bind=engine)()
    from sqlalchemy import create_engine as ce
    lite = sessionmaker(bind=(e := ce("sqlite://")))()
    Base.metadata.create_all(e)
    fake = FakeEmbedder()
    try:
        for db in (pg, lite):
            seed(db, load_seed())
            for g in db.scalars(select(goal_service.Goal)):
                g.status = "active"
            db.commit()
            embedding_service.reindex(db, fake)
        q = fake.embed(["Mathematics – difficulty with subtraction word problems"])[0]
        a = [(h.goal.code, round(h.score, 4)) for h in vector_search(pg, q, model=fake.model, k=5, domain_code="mathematics")]
        b = [(h.goal.code, round(h.score, 4)) for h in vector_search(lite, q, model=fake.model, k=5, domain_code="mathematics")]
        assert a == b
    finally:
        pg.close()
        Base.metadata.drop_all(engine)
