"""Stage 12: year-end evaluation - de-identified evidence, prompt, AI validation, fallback, editor."""

import json
from datetime import date

import pytest

from app.core.config import get_settings
from app.main import app
from app.models.user import Role
from app.prompts import YEAR_END_PROMPT_VERSION, load_prompt
from app.routers.evaluations import get_model_factory
from app.services import evaluation_evidence, progress_service
from app.services.evaluation_ai import AiUnavailable, EvaluationDraft, ModelReply
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

TODAY = date(2026, 3, 1)


class FrozenDate(date):
    @classmethod
    def today(cls):
        return TODAY


@pytest.fixture(autouse=True)
def frozen(monkeypatch):
    monkeypatch.setattr(progress_service, "date", FrozenDate)
    monkeypatch.setattr(evaluation_evidence, "date", FrozenDate)


@pytest.fixture
def ai_on(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "evaluation_ai_enabled", True)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-not-real")
    monkeypatch.setattr(settings, "openai_model", "gpt-test-model")


RATING = {"met": "met", "on_track": "progressing", "below_aim": "limited_progress", "no_recent_data": "limited_progress"}


def good_draft(package: dict, **overrides) -> EvaluationDraft:
    goals = [
        {"goal_id": g["id"], "rating": RATING.get(g["computed_status"], "insufficient_evidence"),
         "narrative": f"[LEARNER] worked on this goal; the latest value was {g['latest_value']} against a target of {g['target_value']}.",
         "evidence_ids": [g["id"]] + [p["id"] for p in package["progress"] if p["goal"] == g["id"]][:2]}
        for g in package["goals"]
    ]
    data = {
        "summary": "[LEARNER] made steady progress this year across the IEP goals, with more practice needed in some areas.",
        "summary_evidence_ids": [package["goals"][0]["id"]],
        "goals": goals,
        "strengths": [{"text": "[LEARNER] recognizes all letters.", "evidence_ids": [f["id"] for f in package["findings"]][:1]}],
        "recommendations": [{"text": "Continue daily subtraction practice with counters.", "evidence_ids": [package["goals"][0]["id"]]}],
    }
    data.update(overrides)
    return EvaluationDraft.model_validate(data)


class FakeModel:
    """Scripted replies. Each script step gets the package and returns a draft, None, or raises."""

    def __init__(self, *steps):
        self.steps = list(steps)
        self.calls: list[str] = []

    def complete(self, instructions, user_input):
        self.calls.append(user_input)
        package = json.loads(user_input.split("EVIDENCE PACKAGE (JSON):\n", 1)[1].split("\n\nYOUR PREVIOUS ANSWER", 1)[0])
        step = self.steps.pop(0) if len(self.steps) > 1 else self.steps[0]
        draft = step(package)
        return ModelReply(draft=draft, raw_text=draft.model_dump_json() if draft else "garbage", model="gpt-test-model-2026")


def use_model(model):
    app.dependency_overrides[get_model_factory] = lambda: (lambda: model)


@pytest.fixture
def setup(client, coord_headers, active):
    """Finalized IEP with progress data, an observation that mentions the learner's name, and an ILAW entry."""
    learner, iep = active(code="EVAL-1")
    lid = learner["id"]
    math = next(g for g in iep["goals"] if g["measurement_method"] == "percent_accuracy")
    for day, value in (("2026-01-10", 35), ("2026-02-10", 45), ("2026-02-24", 55)):
        r = client.post(f"/api/learners/{lid}/progress", headers=coord_headers,
                        json={"evidence_type": "probe", "iep_goal_id": math["id"], "value": value, "recorded_on": day})
        assert r.status_code == 201, r.text
    client.post(f"/api/learners/{lid}/progress", headers=coord_headers, json={
        "evidence_type": "observation", "recorded_on": "2026-02-12",
        "note": f"{learner['first_name']} {learner['last_name']} helped a classmate. Call 0917 123 4567 or ana@example.com."})
    client.post(f"/api/learners/{lid}/progress", headers=coord_headers, json={
        "evidence_type": "grade", "recorded_on": "2026-02-15", "subject": "Mathematics", "grading_period": "Q3", "value": 82})
    entry = log(client, coord_headers, lid, activity_date="2026-02-05").json()
    # Only CONFIRMED goal links count as evidence.
    client.post(f"/api/ilaw-links/{entry['alignments'][0]['id']}/confirm", headers=coord_headers)
    yield learner, iep
    app.dependency_overrides.pop(get_model_factory, None)


def preview(client, headers, lid):
    response = client.get(f"/api/learners/{lid}/evaluations/preview", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


# --- Evidence package / de-identification --------------------------------------------------


def test_package_is_deidentified(client, coord_headers, setup, coordinator):
    learner, iep = setup
    data = preview(client, coord_headers, learner["id"])
    text = json.dumps(data["package"])
    for secret in (learner["first_name"], learner["last_name"], learner["learner_code"], learner["birth_date"],
                   coordinator.name, "0917 123 4567", "ana@example.com", "2026-02-12"):
        assert secret not in text, secret
    assert "[LEARNER]" in text and "[PHONE REMOVED]" in text and "[EMAIL REMOVED]" in text
    pkg = data["package"]
    assert [g["id"] for g in pkg["goals"]] == [f"G{i}" for i in range(1, len(iep["goals"]) + 1)]
    assert pkg["learner"] == {"ref": "[LEARNER]", "grade": "Grade 3", "age_years": 9}
    assert any(p["id"].startswith("P") and p["week"] for p in pkg["progress"])
    assert pkg["observations"] and pkg["grades"] and pkg["activities"] and pkg["findings"]
    assert data["evidence_count"] == len(pkg["goals"]) + sum(len(pkg[k]) for k in ("findings", "progress", "activities", "observations", "grades"))
    assert data["ai_enabled"] is False and len(data["evidence_hash"]) == 64
    # Stable: the same evidence gives the same hash.
    assert preview(client, coord_headers, learner["id"])["evidence_hash"] == data["evidence_hash"]


def test_assert_clean_blocks_leaks(db_session, setup):
    from app.models.learner import Learner

    learner_row = db_session.get(Learner, setup[0]["id"])
    with pytest.raises(evaluation_evidence.IdentifierLeak):
        evaluation_evidence.assert_clean(f"Notes about {learner_row.first_name}", learner_row, [])
    with pytest.raises(evaluation_evidence.IdentifierLeak):
        evaluation_evidence.assert_clean(learner_row.learner_code, learner_row, [])
    evaluation_evidence.assert_clean("the learner will read", learner_row, [])  # ordinary words are fine


def test_prompt_is_versioned_with_grounding_rules():
    text = load_prompt(YEAR_END_PROMPT_VERSION)
    assert YEAR_END_PROMPT_VERSION == "year-end-v1"
    for rule in ("ONLY information", "evidence_ids", "Never invent", "computed_status", "[LEARNER]"):
        assert rule in text
    with pytest.raises(ValueError):
        load_prompt("year-end-v999")


# --- AI path ---------------------------------------------------------------------------------


def test_ai_draft_saved_with_provenance(client, coord_headers, setup, ai_on):
    learner, iep = setup
    model = FakeModel(good_draft)
    use_model(model)
    pv = preview(client, coord_headers, learner["id"])
    assert pv["ai_enabled"] and pv["ai_configured"]
    response = client.post(f"/api/learners/{learner['id']}/evaluations/generate", headers=coord_headers,
                           json={"evidence_hash": pv["evidence_hash"]})
    assert response.status_code == 201, response.text
    ev = response.json()
    assert ev["source"] == "ai" and ev["fallback_reason"] is None and ev["status"] == "draft"
    assert ev["model"] == "gpt-test-model-2026" and ev["prompt_version"] == "year-end-v1"
    assert ev["evidence_hash"] == pv["evidence_hash"] and ev["evidence_snapshot"] == pv["package"]
    assert set(ev["evidence_ids"]) == {g["id"] for g in pv["package"]["goals"]} | {i["id"] for k in ("findings", "progress", "activities", "observations", "grades") for i in pv["package"][k]}
    assert len(model.calls) == 1
    # Content is re-identified for staff; the raw response stays de-identified.
    assert ev["content"]["summary"].startswith(learner["first_name"])
    assert "[LEARNER]" in ev["raw_response"] and learner["first_name"] not in ev["raw_response"]
    assert [g["iep_goal_id"] for g in ev["content"]["goals"]] == [g["id"] for g in iep["goals"]]


def test_invalid_reply_is_retried_once_then_falls_back(client, coord_headers, setup, ai_on):
    learner, _ = setup

    def bad_ids(pkg):
        return good_draft(pkg, summary_evidence_ids=["X99"])

    # First bad, then good -> AI draft after one re-ask that lists the error.
    model = FakeModel(bad_ids, good_draft)
    use_model(model)
    pv = preview(client, coord_headers, learner["id"])
    ev = client.post(f"/api/learners/{learner['id']}/evaluations/generate", headers=coord_headers,
                     json={"evidence_hash": pv["evidence_hash"]}).json()
    assert ev["source"] == "ai" and len(model.calls) == 2 and "X99" in model.calls[1]
    client.delete(f"/api/evaluations/{ev['id']}", headers=coord_headers)

    # Always bad -> manual fallback with the reason recorded.
    use_model(FakeModel(bad_ids))
    ev = client.post(f"/api/learners/{learner['id']}/evaluations/generate", headers=coord_headers,
                     json={"evidence_hash": pv["evidence_hash"]}).json()
    assert ev["source"] == "manual" and "unknown evidence IDs" in ev["fallback_reason"]
    assert ev["generation_error"] == ev["fallback_reason"]
    assert all("[Describe" in g["narrative"] for g in ev["content"]["goals"])


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda pkg: good_draft(pkg, goals=good_draft(pkg).model_dump()["goals"][:-1]), "Goal entries must be exactly"),
        (lambda pkg: good_draft(pkg, goals=[{**g, "rating": "met"} for g in good_draft(pkg).model_dump()["goals"]]), "computed status"),
        (lambda pkg: good_draft(pkg, summary="Sample Match did very well this year in every goal area."), "identifiers"),
        (lambda pkg: good_draft(pkg, summary="[TEACHER] says [LEARNER] did well across all goal areas."), "unknown placeholders"),
        (lambda pkg: None, "required JSON format"),
    ],
)
def test_validation_rejects_bad_drafts(client, coord_headers, setup, ai_on, mutate, expected):
    learner, _ = setup
    use_model(FakeModel(mutate))
    pv = preview(client, coord_headers, learner["id"])
    ev = client.post(f"/api/learners/{learner['id']}/evaluations/generate", headers=coord_headers,
                     json={"evidence_hash": pv["evidence_hash"]}).json()
    assert ev["source"] == "manual" and expected in ev["fallback_reason"]


def test_api_errors_fall_back_to_manual(client, coord_headers, setup, ai_on):
    learner, _ = setup

    def boom(pkg):
        raise AiUnavailable("OpenAI rejected the API key.")

    use_model(FakeModel(boom))
    pv = preview(client, coord_headers, learner["id"])
    ev = client.post(f"/api/learners/{learner['id']}/evaluations/generate", headers=coord_headers,
                     json={"evidence_hash": pv["evidence_hash"]}).json()
    assert ev["source"] == "manual" and ev["fallback_reason"] == "OpenAI rejected the API key."


def test_missing_key_disables_ai(client, coord_headers, setup, monkeypatch):
    """If the key is removed after the preview, generate refuses (nothing is sent)."""
    settings = get_settings()
    monkeypatch.setattr(settings, "evaluation_ai_enabled", True)
    monkeypatch.setattr(settings, "openai_api_key", "sk-x")
    monkeypatch.setattr(settings, "openai_model", "m")
    app.dependency_overrides.pop(get_model_factory, None)
    learner, _ = setup
    pv = preview(client, coord_headers, learner["id"])
    monkeypatch.setattr(settings, "openai_api_key", "")  # key disappears before the call
    monkeypatch.setattr(settings, "evaluation_ai_enabled", True)
    response = client.post(f"/api/learners/{learner['id']}/evaluations/generate", headers=coord_headers,
                           json={"evidence_hash": pv["evidence_hash"]})
    assert response.status_code == 409 and response.json()["error"]["code"] == "ai_disabled"


def test_ai_disabled_and_hash_mismatch(client, coord_headers, setup, ai_on, monkeypatch):
    learner, _ = setup
    use_model(FakeModel(good_draft))
    wrong = client.post(f"/api/learners/{learner['id']}/evaluations/generate", headers=coord_headers, json={"evidence_hash": "0" * 64})
    assert wrong.status_code == 409 and wrong.json()["error"]["code"] == "evidence_changed"
    monkeypatch.setattr(get_settings(), "evaluation_ai_enabled", False)
    pv = preview(client, coord_headers, learner["id"])
    off = client.post(f"/api/learners/{learner['id']}/evaluations/generate", headers=coord_headers, json={"evidence_hash": pv["evidence_hash"]})
    assert off.status_code == 409 and off.json()["error"]["code"] == "ai_disabled"
    # Manual always works.
    assert client.post(f"/api/learners/{learner['id']}/evaluations/manual", headers=coord_headers).status_code == 201


# --- Editor / finalize -------------------------------------------------------------------------------


def test_manual_edit_and_finalize(client, coord_headers, setup, make_user, login):
    learner, iep = setup
    ev = client.post(f"/api/learners/{learner['id']}/evaluations/manual", headers=coord_headers)
    assert ev.status_code == 201
    ev = ev.json()
    assert ev["source"] == "manual" and ev["model"] is None and ev["prompt_version"] is None
    assert len(ev["content"]["goals"]) == len(iep["goals"])
    assert client.post(f"/api/learners/{learner['id']}/evaluations/manual", headers=coord_headers).json()["error"]["code"] == "draft_exists"

    incomplete = client.post(f"/api/evaluations/{ev['id']}/finalize", headers=coord_headers)
    assert incomplete.status_code == 422
    assert {d["field"] for d in incomplete.json()["error"]["details"]} >= {"summary", "goals.0.narrative"}

    content = ev["content"]
    content["summary"] = "A good year overall with clear growth in mathematics and motor skills."
    for g in content["goals"]:
        g["narrative"] = "Progress was steady according to the recorded data points."
    content["recommendations"] = [{"text": "Keep practising subtraction daily.", "evidence_ids": ["G1"]}]
    bad = {**content, "goals": content["goals"][:-1]}
    assert client.patch(f"/api/evaluations/{ev['id']}", headers=coord_headers, json=bad).status_code == 422
    unknown = {**content, "strengths": [{"text": "Kind to peers.", "evidence_ids": ["Z1"]}]}
    assert client.patch(f"/api/evaluations/{ev['id']}", headers=coord_headers, json=unknown).status_code == 422
    saved = client.patch(f"/api/evaluations/{ev['id']}", headers=coord_headers, json=content)
    assert saved.status_code == 200, saved.text

    teacher = make_user(Role.TEACHER)
    client.post(f"/api/learners/{learner['id']}/assignments", headers=coord_headers, json={"user_id": teacher.id})
    assert client.post(f"/api/evaluations/{ev['id']}/finalize", headers=login(teacher)).status_code == 403

    final = client.post(f"/api/evaluations/{ev['id']}/finalize", headers=coord_headers)
    assert final.status_code == 200 and final.json()["status"] == "finalized" and final.json()["read_only"]
    assert client.patch(f"/api/evaluations/{ev['id']}", headers=coord_headers, json=content).json()["error"]["code"] == "evaluation_read_only"
    assert client.delete(f"/api/evaluations/{ev['id']}", headers=coord_headers).status_code == 409
    again = client.post(f"/api/learners/{learner['id']}/evaluations/manual", headers=coord_headers)
    assert again.status_code == 409 and again.json()["error"]["code"] == "evaluation_exists"

    listed = client.get(f"/api/learners/{learner['id']}/evaluations", headers=coord_headers).json()["items"]
    assert [e["status"] for e in listed] == ["finalized"]
    summary = client.get(f"/api/learners/{learner['id']}/summary", headers=coord_headers).json()["modules"]["evaluations"]
    assert summary["available"] and summary["count"] == 1


def test_evaluation_permissions(client, coord_headers, setup, make_user, login):
    learner, _ = setup
    ev = client.post(f"/api/learners/{learner['id']}/evaluations/manual", headers=coord_headers).json()
    head = login(make_user(Role.SCHOOL_HEAD))
    assert client.get(f"/api/evaluations/{ev['id']}", headers=head).status_code == 200
    assert client.get(f"/api/learners/{learner['id']}/evaluations", headers=head).status_code == 200
    assert client.get(f"/api/learners/{learner['id']}/evaluations/preview", headers=head).status_code == 403
    assert client.post(f"/api/learners/{learner['id']}/evaluations/manual", headers=head).status_code == 403
    stranger = login(make_user(Role.TEACHER))
    assert client.get(f"/api/evaluations/{ev['id']}", headers=stranger).status_code == 404
    assert client.get(f"/api/learners/{learner['id']}/evaluations/preview", headers=stranger).status_code == 404
    assert client.get(f"/api/evaluations/{ev['id']}").status_code == 401


# --- Real OpenAI client: error mapping without network -------------------------------------------


def test_openai_client_maps_errors(monkeypatch, ai_on):
    import httpx2
    import openai

    from app.services.evaluation_ai import OpenAIEvaluationModel

    model = OpenAIEvaluationModel()
    request = httpx2.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx2.Response(401, request=request)
    cases = [
        (openai.AuthenticationError("bad key", response=response, body=None), "rejected the API key"),
        (openai.APITimeoutError(request=request), "did not answer in time"),
        (openai.APIConnectionError(request=request), "network problem"),
        (openai.RateLimitError("slow down", response=httpx2.Response(429, request=request), body=None), "rate limit"),
    ]
    for exc, message in cases:
        def raise_(*args, exc=exc, **kwargs):
            raise exc
        monkeypatch.setattr(model.client.responses, "parse", raise_)
        with pytest.raises(AiUnavailable, match=message):
            model.complete("instructions", "input")

    captured = {}

    class Parsed:
        output_parsed = None
        output_text = "{}"
        model = "gpt-test-model-2026-01"

    def fake_parse(**kwargs):
        captured.update(kwargs)
        return Parsed()

    monkeypatch.setattr(model.client.responses, "parse", fake_parse)
    reply = model.complete("rules", "package")
    assert reply.model == "gpt-test-model-2026-01"
    assert captured["model"] == "gpt-test-model" and captured["store"] is False
    assert captured["text_format"] is EvaluationDraft and captured["instructions"] == "rules"


def test_openai_client_requires_configuration(monkeypatch):
    from app.services.evaluation_ai import OpenAIEvaluationModel

    monkeypatch.setattr(get_settings(), "openai_api_key", "")
    with pytest.raises(AiUnavailable):
        OpenAIEvaluationModel()
