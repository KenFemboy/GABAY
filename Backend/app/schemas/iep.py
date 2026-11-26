from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field

from app.models.goal import MeasurementMethod, TargetUnit
from app.models.iep import IepGoalSource, IepStatus
from app.schemas.common import strip_optional, strip_required
from app.services.extraction.schema import FindingCategory, FindingDomain


def _text(max_len: int):
    return Annotated[Annotated[str, Field(max_length=max_len)] | None, BeforeValidator(strip_optional)]


class TeamMember(BaseModel):
    name: Annotated[str, Field(max_length=150), AfterValidator(strip_required)]
    role: Annotated[str, Field(max_length=100), AfterValidator(strip_required)]


class IepUpdate(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    annual_review_date: date | None = None
    accommodations: _text(5000) = None
    services: _text(5000) = None
    notes: _text(5000) = None
    team_members: Annotated[list[TeamMember], Field(max_length=20)] | None = None
    amendment_reason: _text(2000) = None


class AmendBody(BaseModel):
    reason: Annotated[str, Field(min_length=5, max_length=2000), AfterValidator(strip_required)]


class IepFindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: FindingCategory
    domain: FindingDomain | None
    text: str
    position: int
    source_finding_id: int | None


class IepFindingCreate(BaseModel):
    category: FindingCategory
    domain: FindingDomain | None = None
    text: Annotated[str, Field(max_length=2000), AfterValidator(strip_required)]


class IepFindingUpdate(BaseModel):
    category: FindingCategory | None = None
    domain: FindingDomain | None = None
    text: Annotated[str, Field(max_length=2000), AfterValidator(strip_required)] | None = None


ReviewDates = Annotated[list[date], Field(max_length=12)]


class IepGoalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int
    source: IepGoalSource
    goal_recommendation_id: int | None
    goal_id: int | None
    goal_version_id: int | None
    goal_code: str | None
    addresses_finding_id: int | None
    domain: FindingDomain | None
    skill_name: str | None
    statement: str
    measurement_method: MeasurementMethod | None
    baseline: str | None
    baseline_value: float | None
    target_value: float | None
    target_unit: TargetUnit | None
    criterion: str | None
    responsible_staff: str | None
    start_date: date | None
    target_date: date | None
    review_dates: list[date]
    match_score: float | None


class IepGoalFields(BaseModel):
    addresses_finding_id: int | None = None
    domain: FindingDomain | None = None
    skill_name: _text(120) = None
    statement: Annotated[Annotated[str, Field(min_length=10, max_length=2000)] | None, BeforeValidator(strip_optional)] = None
    measurement_method: MeasurementMethod | None = None
    baseline: _text(2000) = None
    baseline_value: Annotated[float, Field(ge=0, le=100000)] | None = None
    target_value: Annotated[float, Field(ge=0, le=100000)] | None = None
    target_unit: TargetUnit | None = None
    criterion: _text(300) = None
    responsible_staff: _text(500) = None
    start_date: date | None = None
    target_date: date | None = None
    review_dates: ReviewDates | None = None


class IepGoalCreate(IepGoalFields):
    goal_id: int | None = None  # from the goal bank; omit for a custom goal


class IssueRead(BaseModel):
    field: str
    message: str
    goal_id: int | None = None


class IepSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    learner_id: int
    school_year: str
    version_number: int
    status: IepStatus
    amends_iep_id: int | None
    amendment_reason: str | None
    start_date: date | None
    end_date: date | None
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    finalized_by_name: str | None
    finalized_at: datetime | None
    read_only: bool
    goal_count: int = 0


class IepRead(IepSummary):
    annual_review_date: date | None
    accommodations: str | None
    services: str | None
    notes: str | None
    team_members: list[dict]
    findings: list[IepFindingRead]
    goals: list[IepGoalRead]
    validation: list[IssueRead]


class IepList(BaseModel):
    items: list[IepSummary]


class ImportResult(BaseModel):
    findings_added: int
    goals_added: int
    iep: IepRead


class OrderBody(BaseModel):
    ids: list[int]
