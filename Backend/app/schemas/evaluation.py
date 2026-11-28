from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.models.evaluation import EvaluationSource, EvaluationStatus, GoalRating
from app.schemas.common import strip_required

EvidenceIds = Annotated[list[Annotated[str, Field(max_length=20)]], Field(max_length=50)]


class CitedItem(BaseModel):
    text: Annotated[str, Field(max_length=1500), AfterValidator(strip_required)]
    evidence_ids: EvidenceIds = []


class GoalItem(BaseModel):
    iep_goal_id: int
    rating: GoalRating
    narrative: Annotated[str, Field(max_length=3000)]
    evidence_ids: EvidenceIds = []


class EvaluationContent(BaseModel):
    summary: Annotated[str, Field(max_length=4000)]
    goals: list[GoalItem]
    strengths: Annotated[list[CitedItem], Field(max_length=10)]
    recommendations: Annotated[list[CitedItem], Field(max_length=10)]


class EvaluationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    learner_id: int
    iep_id: int
    school_year: str
    status: EvaluationStatus
    source: EvaluationSource
    model: str | None
    prompt_version: str | None
    generation_error: str | None
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    finalized_by_name: str | None
    finalized_at: datetime | None
    read_only: bool


class EvaluationRead(EvaluationSummary):
    evidence_ids: list[str]
    evidence_hash: str | None
    evidence_snapshot: dict
    validation_warnings: list[str]
    raw_response: str | None  # de-identified model output, for review
    content: dict
    fallback_reason: str | None = None


class EvaluationList(BaseModel):
    items: list[EvaluationSummary]


class PreviewRead(BaseModel):
    ai_enabled: bool
    ai_configured: bool
    evidence_hash: str
    evidence_count: int
    package: dict
    sent_to: str


class GenerateBody(BaseModel):
    evidence_hash: Annotated[str, Field(min_length=64, max_length=64)]
