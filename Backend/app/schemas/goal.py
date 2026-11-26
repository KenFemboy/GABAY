from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field

from app.models.goal import GoalStatus, GradeBand, MeasurementMethod, TargetUnit
from app.schemas.common import strip_optional, strip_required

Code = Annotated[str, Field(min_length=2, max_length=32, pattern=r"^[a-z][a-z0-9_]*$")]
Name = Annotated[str, Field(max_length=120), AfterValidator(strip_required)]
OptionalText = Annotated[
    Annotated[str, Field(max_length=2000)] | None, BeforeValidator(strip_optional)
]


# --- Taxonomy ------------------------------------------------------------------


class SkillRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    domain_id: int
    code: str
    name: str
    description: str | None
    sort_order: int
    is_active: bool


class DomainRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    description: str | None
    sort_order: int
    is_active: bool
    skills: list[SkillRead]


class TaxonomyRead(BaseModel):
    domains: list[DomainRead]


class DomainCreate(BaseModel):
    code: Code
    name: Name
    description: OptionalText = None
    sort_order: int = 0


class DomainUpdate(BaseModel):
    name: Name | None = None
    description: OptionalText = None
    sort_order: int | None = None
    is_active: bool | None = None


class SkillCreate(BaseModel):
    domain_id: int
    code: Code
    name: Name
    description: OptionalText = None
    sort_order: int = 0


class SkillUpdate(BaseModel):
    domain_id: int | None = None
    name: Name | None = None
    description: OptionalText = None
    sort_order: int | None = None
    is_active: bool | None = None


# --- Goals -----------------------------------------------------------------------


class TaxonomyRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str


class GoalVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_number: int
    domain: TaxonomyRef
    skill: TaxonomyRef
    statement: str
    measurement_method: MeasurementMethod
    target_value: float
    target_unit: TargetUnit
    criterion: str | None
    grade_band: GradeBand
    change_note: str | None
    created_by_name: str
    created_at: datetime
    usage_count: int


class GoalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    status: GoalStatus
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    current_version: GoalVersionRead
    in_use: bool = False


class GoalDetail(GoalRead):
    versions: list[GoalVersionRead]
    indexed: bool = False


class GoalList(BaseModel):
    items: list[GoalRead]
    total: int


class GoalFields(BaseModel):
    domain_id: int
    skill_id: int
    statement: Annotated[str, Field(min_length=10, max_length=2000), AfterValidator(strip_required)]
    measurement_method: MeasurementMethod
    target_value: Annotated[float, Field(ge=0, le=100000)]
    target_unit: TargetUnit
    criterion: Annotated[Annotated[str, Field(max_length=300)] | None, BeforeValidator(strip_optional)] = None
    grade_band: GradeBand = GradeBand.ANY


class GoalCreate(GoalFields):
    code: Annotated[str, Field(max_length=16, pattern=r"^[A-Za-z]{2,4}-\d{1,4}$")] | None = None
    change_note: Annotated[str | None, Field(max_length=300)] = None


class GoalUpdate(BaseModel):
    domain_id: int | None = None
    skill_id: int | None = None
    statement: Annotated[str, Field(min_length=10, max_length=2000), AfterValidator(strip_required)] | None = None
    measurement_method: MeasurementMethod | None = None
    target_value: Annotated[float, Field(ge=0, le=100000)] | None = None
    target_unit: TargetUnit | None = None
    criterion: Annotated[Annotated[str, Field(max_length=300)] | None, BeforeValidator(strip_optional)] = None
    grade_band: GradeBand | None = None
    change_note: Annotated[str | None, Field(max_length=300)] = None


class GoalUpdateResult(BaseModel):
    goal: GoalDetail
    new_version: bool


class IndexStatusRead(BaseModel):
    model: str
    active_goals: int
    indexed: int
    missing_or_stale: int


class ReindexResult(BaseModel):
    created: int
    updated: int
    unchanged: int
    removed: int
    status: IndexStatusRead


class SearchHitRead(BaseModel):
    goal: GoalRead
    score: float


class SearchResult(BaseModel):
    items: list[SearchHitRead]
