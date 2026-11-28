from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from app.models.progress import EvidenceType, GradingPeriod, ProgressUnit
from app.schemas.common import strip_optional


def _opt(max_len: int):
    return Annotated[Annotated[str, Field(max_length=max_len)] | None, BeforeValidator(strip_optional)]


class RecordBase(BaseModel):
    iep_goal_id: int | None = None
    ilaw_entry_id: int | None = None
    value: Annotated[float, Field(ge=-1000000, le=1000000)] | None = None
    out_of: Annotated[float, Field(ge=0, le=1000)] | None = None
    # Alternative to value for percent goals: converted on the server.
    correct: Annotated[float, Field(ge=0, le=10000)] | None = None
    total: Annotated[float, Field(gt=0, le=10000)] | None = None
    unit: ProgressUnit | None = None
    subject: _opt(60) = None
    grading_period: GradingPeriod | None = None
    note: _opt(5000) = None


class RecordCreate(RecordBase):
    evidence_type: EvidenceType
    recorded_on: date


class RecordUpdate(RecordBase):
    evidence_type: EvidenceType | None = None
    recorded_on: date | None = None


class RecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    learner_id: int
    iep_id: int
    iep_goal_id: int | None
    ilaw_entry_id: int | None
    evidence_type: EvidenceType
    value: float | None
    out_of: float | None
    unit: ProgressUnit | None
    subject: str | None
    grading_period: GradingPeriod | None
    recorded_on: date
    note: str | None
    created_by_name: str
    created_at: datetime


class RecordList(BaseModel):
    items: list[RecordRead]


class AimPoint(BaseModel):
    date: date
    value: float


class GoalBrief(BaseModel):
    id: int
    number: int
    goal_code: str | None
    domain: str | None
    statement: str
    measurement_method: str | None
    target_unit: str | None
    criterion: str | None


class StatusRead(BaseModel):
    status: str
    latest: float | None
    expected: float | None
    gap: float | None
    last_recorded_on: date | None
    decreasing: bool


class GoalProgressRead(BaseModel):
    goal: GoalBrief
    baseline_value: float | None
    baseline: str | None
    target_value: float | None
    start_date: date | None
    target_date: date | None
    review_dates: list[date]
    status: StatusRead
    aim_start: AimPoint | None
    aim_end: AimPoint | None
    points: list[RecordRead]
    other: list[RecordRead]


class LearnerProgress(BaseModel):
    iep_id: int | None
    iep_version: int | None
    goals: list[GoalProgressRead]


class TimelineItem(BaseModel):
    kind: str
    id: int
    date: date
    title: str | None
    summary: str | None
    value: float | None
    out_of: float | None
    unit: str | None
    grading_period: str | None
    goal_ids: list[int]
    created_by_name: str


class Timeline(BaseModel):
    items: list[TimelineItem]


class AttentionRow(BaseModel):
    learner_id: int
    learner_name: str
    learner_code: str
    grade_level: str
    section: str
    iep_id: int
    progress: GoalProgressRead


class AttentionList(BaseModel):
    items: list[AttentionRow]
