from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field

from app.models.ilaw import AlignmentSource, AlignmentStatus
from app.schemas.common import strip_optional, strip_required


def _opt(max_len: int):
    return Annotated[Annotated[str, Field(max_length=max_len)] | None, BeforeValidator(strip_optional)]


Title = Annotated[str, Field(max_length=150), AfterValidator(strip_required)]
Description = Annotated[str, Field(max_length=5000), AfterValidator(strip_required)]
Duration = Annotated[int, Field(ge=1, le=480)]


class EntryCreate(BaseModel):
    activity_date: date
    title: Title
    description: Description
    materials: _opt(2000) = None
    learner_response: _opt(5000) = None
    duration_minutes: Duration | None = None
    notes: _opt(5000) = None


class EntryUpdate(BaseModel):
    activity_date: date | None = None
    title: Title | None = None
    description: Description | None = None
    materials: _opt(2000) = None
    learner_response: _opt(5000) = None
    duration_minutes: Duration | None = None
    notes: _opt(5000) = None


class GoalRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    iep_id: int
    position: int
    goal_code: str | None
    domain: str | None
    statement: str


class LinkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    iep_goal_id: int
    goal: GoalRef
    source: AlignmentSource
    status: AlignmentStatus
    score: float | None
    rank: int | None
    model_version: str | None
    decided_by_name: str | None
    decided_at: datetime | None


class EntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    learner_id: int
    iep_id: int
    activity_date: date
    title: str
    description: str
    materials: str | None
    learner_response: str | None
    duration_minutes: int | None
    notes: str | None
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    alignments: list[LinkRead]
    suggestions_error: str | None = None


class EntryList(BaseModel):
    items: list[EntryRead]
    total: int


class ActiveIepRead(BaseModel):
    id: int
    version_number: int
    school_year: str
    start_date: date | None
    end_date: date | None
    goals: list[GoalRef]


class ActiveIep(BaseModel):
    iep: ActiveIepRead | None


class GoalChoice(BaseModel):
    iep_goal_id: int
