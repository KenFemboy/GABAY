"""Stage 7: goal bank - taxonomy, goals, versioning, status, embeddings, seed."""

import hashlib
import os
import re
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.main import app
from app.models.goal import Goal, GoalDomain, GoalEmbedding, GoalSkill, GoalVersion
from app.models.user import Role
from app.scripts.seed_goal_bank import load_seed, seed
from app.services import embedding_service, goal_service
from app.services.embedding_service import get_embedder


class FakeEmbedder:
    """Deterministic bag-of-words hashing embedder: shared words -> similar vectors."""

    model = "fake-bow-64"

    def __init__(self):
        self.calls = 0
        self.texts: list[str] = []

    def embed(self, texts):
        self.calls += 1
        self.texts.extend(texts)
        out = np.zeros((len(texts), 64), dtype=np.float32)
        for i, text in enumerate(texts):
            for word in re.findall(r"[a-z]+", text.lower()):
                if len(word) > 3:
                    out[i, int(hashlib.md5(word.encode()).hexdigest(), 16) % 64] += 1
        return embedding_service._normalize(out)


@pytest.fixture
def embedder(client):
    fake = FakeEmbedder()
    app.dependency_overrides[get_embedder] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_embedder, None)


@pytest.fixture
def coord_headers(login, make_user):
    return login(make_user(Role.SNED_COORDINATOR))


@pytest.fixture
def taxonomy(db_session):
    """Two domains with skills, created directly."""
    reading = GoalDomain(code="reading", name="Reading", sort_order=1)
    math = GoalDomain(code="mathematics", name="Mathematics", sort_order=2)
    db_session.add_all([reading, math])
    db_session.flush()
    skills = {
        "decoding": GoalSkill(domain_id=reading.id, code="decoding", name="Phonics and decoding"),
        "comprehension": GoalSkill(domain_id=reading.id, code="comprehension", name="Comprehension"),
        "subtraction": GoalSkill(domain_id=math.id, code="addition_subtraction", name="Addition and subtraction"),
    }
    db_session.add_all(skills.values())
    db_session.commit()
    return {"reading": reading, "math": math, **skills}


def goal_payload(t, **overrides):
    data = {
        "domain_id": t["reading"].id,
        "skill_id": t["decoding"].id,
        "statement": "Given 20 CVC words, the learner will decode them with 80% accuracy.",
        "measurement_method": "percent_accuracy",
        "target_value": 80,
        "target_unit": "percent",
        "criterion": "in 3 consecutive probes",
        "grade_band": "K-3",
    }
    data.update(overrides)
    return data


def create(client, headers, t, **overrides):
    response = client.post("/api/goals", headers=headers, json=goal_payload(t, **overrides))
    assert response.status_code == 201, response.text
    return response.json()


def activate(client, headers, goal_id):
    response = client.post(f"/api/goals/{goal_id}/activate", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


# --- CRUD, validation, permissions ---------------------------------------------


def test_create_goal_draft_with_generated_code(client, coord_headers, taxonomy, embedder):
    goal = create(client, coord_headers, taxonomy)
    assert goal["code"] == "RD-001" and goal["status"] == "draft"
    v = goal["current_version"]
    assert v["version_number"] == 1 and v["domain"]["code"] == "reading" and v["skill"]["code"] == "decoding"
    assert v["target_value"] == 80 and v["measurement_method"] == "percent_accuracy"
    assert goal["versions"][0]["id"] == v["id"] and goal["in_use"] is False and goal["indexed"] is False
    assert create(client, coord_headers, taxonomy)["code"] == "RD-002"

    custom = create(client, coord_headers, taxonomy, code="rd-050")
    assert custom["code"] == "RD-050"
    dup = client.post("/api/goals", headers=coord_headers, json={**goal_payload(taxonomy), "code": "RD-050"})
    assert dup.status_code == 409


def test_goal_validation(client, coord_headers, taxonomy, embedder):
    bad_skill = client.post(
        "/api/goals", headers=coord_headers, json=goal_payload(taxonomy, skill_id=taxonomy["subtraction"].id)
    )
    assert bad_skill.status_code == 422 and bad_skill.json()["error"]["code"] == "invalid_skill"
    for field, value in [("measurement_method", "vibes"), ("target_unit", "apples"), ("statement", "short"),
                         ("target_value", -1), ("grade_band", "12-13")]:
        r = client.post("/api/goals", headers=coord_headers, json=goal_payload(taxonomy, **{field: value}))
        assert r.status_code == 422, field


def test_readers_see_only_active_goals(client, coord_headers, taxonomy, make_user, login, embedder):
    draft = create(client, coord_headers, taxonomy)
    active = create(client, coord_headers, taxonomy, statement="Given a Grade 1 passage, the learner will read 40 words per minute.")
    activate(client, coord_headers, active["id"])

    for role in (Role.TEACHER, Role.SCHOOL_HEAD):
        headers = login(make_user(role))
        listed = client.get("/api/goals", headers=headers).json()
        assert [g["id"] for g in listed["items"]] == [active["id"]]
        assert client.get(f"/api/goals/{draft['id']}", headers=headers).status_code == 404
        assert client.get(f"/api/goals/{active['id']}", headers=headers).status_code == 200
        assert client.post("/api/goals", headers=headers, json=goal_payload(taxonomy)).status_code == 403
        assert client.post(f"/api/goals/{active['id']}/archive", headers=headers).status_code == 403
        assert client.get("/api/goals/index-status", headers=headers).status_code == 403

    admin = login(make_user(Role.SYSTEM_ADMIN))
    assert client.get("/api/goals", headers=admin).status_code == 403
    assert client.get("/api/goals").status_code == 401
    # The Coordinator sees both and can filter by status.
    assert client.get("/api/goals", headers=coord_headers).json()["total"] == 2
    assert client.get("/api/goals?status=draft", headers=coord_headers).json()["items"][0]["id"] == draft["id"]


def test_goal_filters(client, coord_headers, taxonomy, embedder):
    create(client, coord_headers, taxonomy)
    create(client, coord_headers, taxonomy, skill_id=taxonomy["comprehension"].id, grade_band="4-6",
           measurement_method="trials", target_value=4, target_unit="trials",
           statement="After reading a passage, the learner will answer inferential questions in 4 of 5 trials.")
    create(client, coord_headers, taxonomy, domain_id=taxonomy["math"].id, skill_id=taxonomy["subtraction"].id,
           statement="Given counters, the learner will solve subtraction problems with 80% accuracy.", grade_band="any")

    def codes(query):
        return sorted(g["code"] for g in client.get(f"/api/goals?{query}", headers=coord_headers).json()["items"])

    assert codes(f"domain={taxonomy['math'].id}") == ["MA-001"]
    assert codes(f"skill={taxonomy['comprehension'].id}") == ["RD-002"]
    assert codes("method=trials") == ["RD-002"]
    assert codes("grade_band=K-3") == ["MA-001", "RD-001"]  # "any" matches every band
    assert codes("q=subtraction") == ["MA-001"]
    assert codes("q=rd-002") == ["RD-002"]


# --- Status ----------------------------------------------------------------------


def test_status_flow_and_delete(client, coord_headers, taxonomy, embedder, db_session):
    goal = create(client, coord_headers, taxonomy)
    gid = goal["id"]
    assert activate(client, coord_headers, gid)["status"] == "active"
    assert client.delete(f"/api/goals/{gid}", headers=coord_headers).status_code == 409  # not a draft
    assert client.post(f"/api/goals/{gid}/archive", headers=coord_headers).json()["status"] == "archived"
    edit = client.patch(f"/api/goals/{gid}", headers=coord_headers, json={"target_value": 90})
    assert edit.status_code == 409 and edit.json()["error"]["code"] == "goal_archived"
    assert activate(client, coord_headers, gid)["status"] == "active"

    draft = create(client, coord_headers, taxonomy)
    assert client.delete(f"/api/goals/{draft['id']}", headers=coord_headers).status_code == 204
    assert db_session.get(Goal, draft["id"]) is None


def test_activation_requires_active_taxonomy(client, coord_headers, taxonomy, embedder):
    goal = create(client, coord_headers, taxonomy)
    client.patch(f"/api/goal-taxonomy/skills/{taxonomy['decoding'].id}", headers=coord_headers, json={"is_active": False})
    response = client.post(f"/api/goals/{goal['id']}/activate", headers=coord_headers)
    assert response.status_code == 422 and response.json()["error"]["code"] == "inactive_taxonomy"


# --- Versioning -------------------------------------------------------------------


def test_edit_unused_goal_in_place(client, coord_headers, taxonomy, embedder):
    goal = create(client, coord_headers, taxonomy)
    result = client.patch(f"/api/goals/{goal['id']}", headers=coord_headers,
                          json={"target_value": 90, "change_note": "Raised target"}).json()
    assert result["new_version"] is False
    assert result["goal"]["current_version"]["version_number"] == 1
    assert result["goal"]["current_version"]["target_value"] == 90
    assert len(result["goal"]["versions"]) == 1
    # No-op edit changes nothing.
    again = client.patch(f"/api/goals/{goal['id']}", headers=coord_headers, json={"target_value": 90}).json()
    assert again["new_version"] is False


def test_edit_used_goal_creates_new_version(client, coord_headers, taxonomy, embedder, db_session):
    goal = create(client, coord_headers, taxonomy)
    activate(client, coord_headers, goal["id"])
    v1_id = goal["current_version"]["id"]
    goal_service.record_goal_usage(db_session, v1_id, "iep_goal", 7)
    goal_service.record_goal_usage(db_session, v1_id, "iep_goal", 7)  # idempotent
    db_session.commit()

    detail = client.get(f"/api/goals/{goal['id']}", headers=coord_headers).json()
    assert detail["in_use"] is True and detail["current_version"]["usage_count"] == 1

    new_text = "Given 20 CVC words, the learner will decode them aloud with 90% accuracy."
    result = client.patch(f"/api/goals/{goal['id']}", headers=coord_headers,
                          json={"statement": new_text, "target_value": 90, "change_note": "Harder"}).json()
    assert result["new_version"] is True
    current = result["goal"]["current_version"]
    assert current["version_number"] == 2 and current["statement"] == new_text and current["usage_count"] == 0
    assert result["goal"]["in_use"] is False
    assert [v["version_number"] for v in result["goal"]["versions"]] == [2, 1]

    db_session.expire_all()
    v1 = db_session.get(GoalVersion, v1_id)
    assert v1.statement == goal_payload(taxonomy)["statement"] and v1.target_value == 80  # unchanged

    # The goal stays active, and a used goal cannot be deleted even as a draft.
    assert result["goal"]["status"] == "active"
    assert db_session.scalar(select(func.count(GoalVersion.id))) == 2


def test_used_draft_cannot_be_deleted(client, coord_headers, taxonomy, embedder, db_session):
    goal = create(client, coord_headers, taxonomy)
    goal_service.record_goal_usage(db_session, goal["current_version"]["id"], "iep_goal", 1)
    db_session.commit()
    response = client.delete(f"/api/goals/{goal['id']}", headers=coord_headers)
    assert response.status_code == 409 and response.json()["error"]["code"] == "goal_in_use"


# --- Taxonomy ---------------------------------------------------------------------


def test_taxonomy_management(client, coord_headers, taxonomy, make_user, login, embedder):
    created = client.post("/api/goal-taxonomy/domains", headers=coord_headers,
                          json={"code": "motor", "name": "Motor skills"})
    assert created.status_code == 201
    assert client.post("/api/goal-taxonomy/domains", headers=coord_headers,
                       json={"code": "motor", "name": "Again"}).status_code == 409
    skill = client.post("/api/goal-taxonomy/skills", headers=coord_headers,
                        json={"domain_id": created.json()["id"], "code": "fine_motor", "name": "Fine motor"})
    assert skill.status_code == 201
    renamed = client.patch(f"/api/goal-taxonomy/skills/{skill.json()['id']}", headers=coord_headers,
                           json={"name": "Fine motor skills", "is_active": False})
    assert renamed.json()["name"] == "Fine motor skills" and renamed.json()["is_active"] is False

    # Readers do not see inactive skills; the Coordinator does.
    teacher = login(make_user(Role.TEACHER))
    t = client.get("/api/goal-taxonomy", headers=teacher).json()["domains"]
    assert all(s["is_active"] for d in t for s in d["skills"])
    c = client.get("/api/goal-taxonomy", headers=coord_headers).json()["domains"]
    assert any(not s["is_active"] for d in c for s in d["skills"])
    assert client.post("/api/goal-taxonomy/domains", headers=teacher, json={"code": "x1", "name": "X"}).status_code == 403

    # A skill used by goals cannot move domains.
    create(client, coord_headers, taxonomy)
    move = client.patch(f"/api/goal-taxonomy/skills/{taxonomy['decoding'].id}", headers=coord_headers,
                        json={"domain_id": taxonomy["math"].id})
    assert move.status_code == 409


# --- Embeddings --------------------------------------------------------------------


def test_reindex_is_idempotent_and_tracks_changes(client, coord_headers, taxonomy, embedder, db_session):
    a = create(client, coord_headers, taxonomy)
    b = create(client, coord_headers, taxonomy, domain_id=taxonomy["math"].id, skill_id=taxonomy["subtraction"].id,
               statement="Given counters, the learner will solve subtraction problems with 80% accuracy.")
    draft = create(client, coord_headers, taxonomy)
    activate(client, coord_headers, a["id"])
    activate(client, coord_headers, b["id"])

    status = client.get("/api/goals/index-status", headers=coord_headers).json()
    assert status == {"model": "fake-bow-64", "active_goals": 2, "indexed": 0, "missing_or_stale": 2}

    first = client.post("/api/goals/reindex", headers=coord_headers).json()
    assert (first["created"], first["updated"], first["unchanged"], first["removed"]) == (2, 0, 0, 0)
    assert first["status"]["indexed"] == 2
    count = db_session.scalar(select(func.count(GoalEmbedding.id)))
    assert count == 2

    second = client.post("/api/goals/reindex", headers=coord_headers).json()
    assert (second["created"], second["updated"], second["unchanged"], second["removed"]) == (0, 0, 2, 0)
    assert db_session.scalar(select(func.count(GoalEmbedding.id))) == 2  # no duplicates

    # Editing an unused active goal -> exactly one row refreshed in place.
    client.patch(f"/api/goals/{a['id']}", headers=coord_headers, json={"statement": a["current_version"]["statement"] + " Daily."})
    assert client.get(f"/api/goals/{a['id']}", headers=coord_headers).json()["indexed"] is False
    third = client.post("/api/goals/reindex", headers=coord_headers).json()
    assert (third["created"], third["updated"], third["unchanged"]) == (0, 1, 1)
    assert client.get(f"/api/goals/{a['id']}", headers=coord_headers).json()["indexed"] is True

    # Archiving removes the vector; drafts are never indexed.
    client.post(f"/api/goals/{b['id']}/archive", headers=coord_headers)
    fourth = client.post("/api/goals/reindex", headers=coord_headers).json()
    assert fourth["removed"] == 1
    ids = set(db_session.scalars(select(GoalEmbedding.goal_version_id)).all())
    assert ids == {a["current_version"]["id"]}
    assert draft["current_version"]["id"] not in ids


def test_new_version_replaces_old_vector(client, coord_headers, taxonomy, embedder, db_session):
    goal = create(client, coord_headers, taxonomy)
    activate(client, coord_headers, goal["id"])
    client.post("/api/goals/reindex", headers=coord_headers)
    goal_service.record_goal_usage(db_session, goal["current_version"]["id"], "iep_goal", 3)
    db_session.commit()
    v2 = client.patch(f"/api/goals/{goal['id']}", headers=coord_headers, json={"target_value": 95}).json()
    assert v2["new_version"] is True
    result = client.post("/api/goals/reindex", headers=coord_headers).json()
    assert (result["created"], result["removed"]) == (1, 1)
    ids = db_session.scalars(select(GoalEmbedding.goal_version_id)).all()
    assert ids == [v2["goal"]["current_version"]["id"]]


def test_semantic_search(client, coord_headers, taxonomy, embedder, make_user, login):
    subtraction = create(client, coord_headers, taxonomy, domain_id=taxonomy["math"].id,
                         skill_id=taxonomy["subtraction"].id,
                         statement="Given counters, the learner will solve single-digit subtraction problems with 80% accuracy.")
    decoding = create(client, coord_headers, taxonomy)
    hidden = create(client, coord_headers, taxonomy, statement="Subtraction subtraction subtraction problems for drafts only.")
    for g in (subtraction, decoding):
        activate(client, coord_headers, g["id"])
    client.post("/api/goals/reindex", headers=coord_headers)

    teacher = login(make_user(Role.TEACHER))
    hits = client.get("/api/goals/search", headers=teacher,
                      params={"q": "Has difficulty with subtraction and word problems."}).json()["items"]
    assert hits[0]["goal"]["id"] == subtraction["id"]
    assert hidden["id"] not in [h["goal"]["id"] for h in hits]  # drafts are never searchable
    assert hits[0]["score"] > hits[-1]["score"]
    assert client.get("/api/goals/search", headers=teacher, params={"q": "ab"}).status_code == 422


def test_embedding_model_unavailable_returns_503(client, coord_headers, taxonomy):
    class Broken:
        model = "broken"

        def embed(self, texts):
            raise embedding_service.EmbeddingUnavailable("no model")

    app.dependency_overrides[get_embedder] = lambda: Broken()
    try:
        goal = create(client, coord_headers, taxonomy)
        activate(client, coord_headers, goal["id"])
        r = client.post("/api/goals/reindex", headers=coord_headers)
        assert r.status_code == 503 and r.json()["error"]["code"] == "embeddings_unavailable"
    finally:
        app.dependency_overrides.pop(get_embedder, None)


def test_reindex_if_needed_only_when_needed(db_session, client, coord_headers, taxonomy, embedder):
    goal = create(client, coord_headers, taxonomy)
    activate(client, coord_headers, goal["id"])
    assert embedding_service.reindex_if_needed(db_session, embedder)["created"] == 1
    calls = embedder.calls
    assert embedding_service.reindex_if_needed(db_session, embedder) is None
    assert embedder.calls == calls


# --- Seed --------------------------------------------------------------------------


def test_seed_loads_drafts_and_is_idempotent(db_session):
    data = load_seed()
    counts = seed(db_session, data)
    n_skills = sum(len(d["skills"]) for d in data["domains"])
    assert counts == {"domains": len(data["domains"]), "skills": n_skills, "goals": len(data["goals"]), "goals_skipped": 0}
    assert len(data["goals"]) >= 45
    statuses = set(db_session.scalars(select(Goal.status)).all())
    assert statuses == {"draft"}
    assert {d.code for d in db_session.scalars(select(GoalDomain))} == {
        "reading", "writing", "mathematics", "behavior_social", "communication", "motor", "self_help", "cognitive", "other"
    }

    # Every starter goal is measurable: a number in the statement and a target.
    for g in data["goals"]:
        assert re.search(r"\d", g["statement"]), g["code"]
        assert g["target_value"] > 0

    # The Coordinator edits one; reseeding changes nothing.
    goal = db_session.scalar(select(Goal).where(Goal.code == "RD-004"))
    goal.current_version.statement = "Edited by the Coordinator: decode 20 CVC words with 85% accuracy."
    db_session.commit()
    again = seed(db_session, data)
    assert again == {"domains": 0, "skills": 0, "goals": 0, "goals_skipped": len(data["goals"])}
    db_session.expire_all()
    assert db_session.scalar(select(Goal).where(Goal.code == "RD-004")).current_version.statement.startswith("Edited")


# --- Real model (optional) --------------------------------------------------------


def _model_cached() -> bool:
    settings = get_settings()
    cache = Path(settings.embedding_cache_dir)
    slug = settings.embedding_model.split("/")[-1]
    return os.environ.get("RUN_EMBEDDING_TESTS") == "1" or (cache.exists() and any(slug in str(p) for p in cache.rglob("*")))


@pytest.mark.skipif(not _model_cached(), reason="embedding model not downloaded (set RUN_EMBEDDING_TESTS=1)")
def test_real_model_ranks_related_goal_first():
    settings = get_settings()
    real = embedding_service.FastEmbedEmbedder(settings.embedding_model, settings.embedding_cache_dir)
    vectors = real.embed([
        "Reads simple CVC words with support.",
        "Phonics and decoding: the learner will decode CVC words with 80% accuracy.",
        "Addition and subtraction: the learner will solve subtraction problems with counters.",
    ])
    assert vectors.shape == (3, 384)
    assert float(vectors[0] @ vectors[1]) > float(vectors[0] @ vectors[2])
