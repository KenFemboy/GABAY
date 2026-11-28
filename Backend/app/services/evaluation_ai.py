"""OpenAI drafting of the year-end evaluation, with strict response validation (Stage 12).

Only the de-identified evidence package is sent. The model must return JSON
matching ``EvaluationDraft`` (requested with the SDK's structured output:
``client.responses.parse(..., text_format=EvaluationDraft)``). The parsed
result is then checked against the package:

1. one entry per goal (G1..Gn), no unknown goals;
2. every item cites at least one evidence ID, and every ID exists;
3. ratings agree with the computed goal status;
4. no identifiers leak and no unknown placeholders appear.

A failed check is sent back to the model once with the errors listed; a
second failure raises ``AiInvalidResponse``. Transport/auth/rate errors raise
``AiUnavailable``. The caller then falls back to a manual draft.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.prompts import YEAR_END_PROMPT_VERSION, load_prompt
from app.services.evaluation_evidence import EvidencePackage, canonical, find_leaks

logger = logging.getLogger(__name__)

Rating = Literal["met", "progressing", "limited_progress", "insufficient_evidence"]
ALLOWED_PLACEHOLDERS = {"[LEARNER]", "[STAFF]", "[SCHOOL]"}
PLACEHOLDER = re.compile(r"\[[A-Z][A-Z _]*\]")


# No length keywords in the schema sent to OpenAI (strict structured output may reject
# them); lengths are enforced in validate_draft instead.
MAX_LEN = {"summary": 4000, "narrative": 3000, "text": 1500}


class CitedText(BaseModel):
    text: str
    evidence_ids: list[str]


class GoalEntry(BaseModel):
    goal_id: str
    rating: Rating
    narrative: str
    evidence_ids: list[str]


class EvaluationDraft(BaseModel):
    summary: str
    summary_evidence_ids: list[str]
    goals: list[GoalEntry]
    strengths: list[CitedText]
    recommendations: list[CitedText]


class AiUnavailable(Exception):
    """The API could not be used (not configured, auth, network, rate limit, refusal...)."""


class AiInvalidResponse(Exception):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass
class ModelReply:
    draft: EvaluationDraft | None
    raw_text: str
    model: str


class EvaluationModel(Protocol):
    def complete(self, instructions: str, user_input: str) -> ModelReply: ...


# --- Real OpenAI client ------------------------------------------------------------------


class OpenAIEvaluationModel:
    """Calls the OpenAI Responses API with structured output."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.evaluation_ai_configured:
            raise AiUnavailable("OpenAI is not configured (OPENAI_API_KEY and OPENAI_MODEL).")
        import openai

        self._openai = openai
        self.model = settings.openai_model
        self.client = openai.OpenAI(
            api_key=settings.openai_api_key, timeout=settings.openai_timeout_seconds, max_retries=1
        )

    def complete(self, instructions: str, user_input: str) -> ModelReply:
        o = self._openai
        try:
            response = self.client.responses.parse(
                model=self.model,
                instructions=instructions,
                input=user_input,
                text_format=EvaluationDraft,
                store=False,  # do not keep the request on OpenAI's side for later retrieval
                max_output_tokens=6000,
            )
        except o.AuthenticationError as exc:
            raise AiUnavailable("OpenAI rejected the API key.") from exc
        except o.PermissionDeniedError as exc:
            raise AiUnavailable("The OpenAI account is not allowed to use this model.") from exc
        except o.NotFoundError as exc:
            raise AiUnavailable(f"OpenAI does not know the model '{self.model}'.") from exc
        except o.RateLimitError as exc:
            raise AiUnavailable("OpenAI rate limit or quota reached. Try again later.") from exc
        except o.APITimeoutError as exc:
            raise AiUnavailable("OpenAI did not answer in time.") from exc
        except o.APIConnectionError as exc:
            raise AiUnavailable("Could not reach OpenAI (network problem).") from exc
        except (o.LengthFinishReasonError, o.ContentFilterFinishReasonError) as exc:
            raise AiUnavailable("OpenAI stopped before finishing the draft.") from exc
        except o.APIStatusError as exc:
            raise AiUnavailable(f"OpenAI returned an error (HTTP {exc.status_code}).") from exc
        except ValidationError as exc:  # the SDK could not parse the structured output
            return ModelReply(draft=None, raw_text=str(exc)[:2000], model=self.model)
        return ModelReply(draft=response.output_parsed, raw_text=response.output_text or "", model=response.model or self.model)


# --- Validation ------------------------------------------------------------------------------


def _ids_in(draft: EvaluationDraft) -> list[tuple[str, list[str]]]:
    items = [("summary", draft.summary_evidence_ids)]
    items += [(f"goal {g.goal_id}", g.evidence_ids) for g in draft.goals]
    items += [(f"strength {i + 1}", s.evidence_ids) for i, s in enumerate(draft.strengths)]
    items += [(f"recommendation {i + 1}", r.evidence_ids) for i, r in enumerate(draft.recommendations)]
    return items


def _expected_rating(status: str) -> set[str]:
    if status == "met":
        return {"met"}
    if status in ("no_data", "not_started", "no_baseline"):
        return {"insufficient_evidence"}
    if status == "on_track":
        return {"progressing", "insufficient_evidence"}
    return {"limited_progress", "progressing", "insufficient_evidence"}  # below_aim / no_recent_data


def validate_draft(draft: EvaluationDraft, evidence: EvidencePackage, learner) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Any error rejects the draft."""
    errors: list[str] = []
    warnings: list[str] = []
    known = set(evidence.ids)

    got = [g.goal_id for g in draft.goals]
    expected = list(evidence.goal_ids)
    if sorted(got) != sorted(expected) or len(set(got)) != len(got):
        errors.append(f"Goal entries must be exactly {', '.join(expected)} (got {', '.join(got) or 'none'}).")

    for label, ids in _ids_in(draft):
        if not ids:
            errors.append(f"{label} cites no evidence IDs.")
        unknown = [i for i in ids if i not in known]
        if unknown:
            errors.append(f"{label} cites unknown evidence IDs: {', '.join(unknown)}.")

    for g in draft.goals:
        status = evidence.goal_status.get(g.goal_id)
        if status and g.rating not in _expected_rating(status):
            errors.append(f"goal {g.goal_id} is rated '{g.rating}' but its computed status is '{status}'.")
        if len(g.narrative.strip()) < 40:
            warnings.append(f"The narrative for {g.goal_id} is very short.")
        if g.goal_id not in g.evidence_ids:
            warnings.append(f"The narrative for {g.goal_id} does not cite the goal itself.")

    texts = [draft.summary] + [g.narrative for g in draft.goals] + [s.text for s in draft.strengths] + [r.text for r in draft.recommendations]
    joined = "\n".join(texts)
    leaks = find_leaks(joined, learner, evidence.staff_terms)
    if leaks:
        errors.append(f"The draft contains identifiers ({', '.join(sorted(set(leaks)))}).")
    odd = {p for p in PLACEHOLDER.findall(joined) if p not in ALLOWED_PLACEHOLDERS}
    if odd:
        errors.append(f"The draft uses unknown placeholders: {', '.join(sorted(odd))}.")
    if not draft.summary.strip():
        errors.append("The summary is empty.")
    if len(draft.summary) > MAX_LEN["summary"]:
        errors.append("The summary is too long.")
    if any(len(g.narrative) > MAX_LEN["narrative"] for g in draft.goals):
        errors.append("A goal narrative is too long.")
    if any(len(i.text) > MAX_LEN["text"] for i in draft.strengths + draft.recommendations):
        errors.append("A strength or recommendation is too long.")
    if not draft.strengths:
        warnings.append("No strengths were listed.")
    if not draft.recommendations:
        warnings.append("No recommendations were listed.")
    return errors, warnings


# --- Generate ------------------------------------------------------------------------------------


@dataclass
class GenerationResult:
    draft: EvaluationDraft
    model: str
    prompt_version: str
    raw_text: str
    warnings: list[str]


def generate(evidence: EvidencePackage, learner, model: EvaluationModel) -> GenerationResult:
    instructions = load_prompt(YEAR_END_PROMPT_VERSION)
    user_input = "EVIDENCE PACKAGE (JSON):\n" + canonical(evidence.package)
    reply = model.complete(instructions, user_input)
    errors = ["The response did not match the required JSON format."] if reply.draft is None else []
    warnings: list[str] = []
    if reply.draft is not None:
        errors, warnings = validate_draft(reply.draft, evidence, learner)
    if errors:
        logger.info("Evaluation draft rejected (%d problems); asking the model once more", len(errors))
        retry_input = (
            user_input
            + "\n\nYOUR PREVIOUS ANSWER WAS REJECTED FOR THESE REASONS - fix all of them:\n- "
            + "\n- ".join(errors)
        )
        reply = model.complete(instructions, retry_input)
        if reply.draft is None:
            raise AiInvalidResponse(["The response did not match the required JSON format."])
        errors, warnings = validate_draft(reply.draft, evidence, learner)
        if errors:
            raise AiInvalidResponse(errors)
    return GenerationResult(reply.draft, reply.model, YEAR_END_PROMPT_VERSION, reply.raw_text, warnings)


def draft_to_json(draft: EvaluationDraft) -> str:
    return json.dumps(draft.model_dump(), ensure_ascii=False)
