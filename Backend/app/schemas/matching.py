from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from app.models.matching import RecommendationSource, RecommendationStatus
from app.schemas.common import strip_optional
from app.schemas.goal import GoalVersionRead

OptionalShort = Annotated[Annotated[str, Field(max_length=300)] | None, BeforeValidator(strip_optional)]


class RunOptions(BaseModel):
    top_k: Annotated[int, Field(ge=1, le=20)] | None = None
    min_score: Annotated[float, Field(ge=0, le=1)] | None = None
    same_domain: bool = True
    use_grade_band: bool = True


class GoalEdits(BaseModel):
    edited_statement: Annotated[Annotated[str, Field(min_length=10, max_length=2000)] | None, BeforeValidator(strip_optional)] = None
    edited_target_value: Annotated[float, Field(ge=0, le=100000)] | None = None
    edited_criterion: OptionalShort = None


class RejectBody(BaseModel):
    reason: OptionalShort = None


class ManualAdd(GoalEdits):
    goal_id: int
    finding_id: int | None = None


class RecommendationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int | None
    finding_id: int | None
    goal_id: int
    goal_code: str
    goal_version: GoalVersionRead
    source: RecommendationSource
    score: float | None
    rank: int | None
    model_version: str | None
    status: RecommendationStatus
    edited_statement: str | None
    edited_target_value: float | None
    edited_criterion: str | None
    final_statement: str
    final_target_value: float
    final_criterion: str | None
    reject_reason: str | None
    decided_by_name: str | None
    decided_at: datetime | None


class NeedRead(BaseModel):
    id: int
    text: str
    domain: str | None
    assessment_id: int
    version_id: int
    suggestions: list[RecommendationRead]


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    learner_id: int
    model: str
    model_version: str
    top_k: int
    min_score: float
    same_domain: bool
    grade_band: str | None
    need_count: int
    created_by_name: str
    created_at: datetime


class RunList(BaseModel):
    items: list[RunRead]


class RunDetail(RunRead):
    needs: list[NeedRead]


class RecommendationsView(BaseModel):
    """Everything the recommendation page needs."""

    run: RunDetail | None
    manual: list[RecommendationRead]
    selected: list[RecommendationRead]
    approved_need_count: int


class SelectedGoals(BaseModel):
    items: list[RecommendationRead]
