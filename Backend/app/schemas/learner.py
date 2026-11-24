import re
from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, field_validator

from app.models.learner import GradeLevel, LearnerStatus, Sex
from app.schemas.common import strip_optional, strip_required

LEARNER_CODE_PATTERN = re.compile(r"^[A-Z0-9-]{1,32}$")
SCHOOL_YEAR_PATTERN = re.compile(r"^(\d{4})-(\d{4})$")
MAX_LEARNER_AGE_YEARS = 30


def normalize_learner_code(value: str) -> str:
    value = value.strip().upper()
    if not value:
        raise ValueError("This field is required.")
    if not LEARNER_CODE_PATTERN.fullmatch(value):
        raise ValueError(
            "Learner code may contain only letters, digits and dashes (up to 32 characters)."
        )
    return value


def validate_school_year(value: str) -> str:
    value = value.strip()
    match = SCHOOL_YEAR_PATTERN.fullmatch(value)
    if not match or int(match.group(2)) != int(match.group(1)) + 1:
        raise ValueError("Use the format 2025-2026.")
    return value


def validate_birth_date(value: date) -> date:
    today = date.today()
    if value > today:
        raise ValueError("Birth date cannot be in the future.")
    if value.year < today.year - MAX_LEARNER_AGE_YEARS:
        raise ValueError(f"Birth date must be within the last {MAX_LEARNER_AGE_YEARS} years.")
    return value


LearnerCode = Annotated[str, Field(max_length=64), AfterValidator(normalize_learner_code)]
SchoolYear = Annotated[str, Field(max_length=16), AfterValidator(validate_school_year)]
NamePart = Annotated[str, Field(max_length=100), AfterValidator(strip_required)]
OptionalNamePart = Annotated[
    Annotated[str, Field(max_length=100)] | None, BeforeValidator(strip_optional)
]
Section = Annotated[str, Field(max_length=50), AfterValidator(strip_required)]
BirthDate = Annotated[date, AfterValidator(validate_birth_date)]


class LearnerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    learner_code: str
    first_name: str
    middle_name: str | None
    last_name: str
    full_name: str
    birth_date: date
    sex: Sex
    grade_level: GradeLevel
    section: str
    school_year: str
    status: LearnerStatus
    created_at: datetime
    updated_at: datetime


class LearnerCreate(BaseModel):
    learner_code: LearnerCode
    first_name: NamePart
    middle_name: OptionalNamePart = None
    last_name: NamePart
    birth_date: BirthDate
    sex: Sex
    grade_level: GradeLevel
    section: Section
    school_year: SchoolYear
    status: LearnerStatus = LearnerStatus.ACTIVE


class LearnerUpdate(BaseModel):
    learner_code: LearnerCode | None = None
    first_name: NamePart | None = None
    middle_name: OptionalNamePart = None
    last_name: NamePart | None = None
    birth_date: BirthDate | None = None
    sex: Sex | None = None
    grade_level: GradeLevel | None = None
    section: Section | None = None
    school_year: SchoolYear | None = None
    status: LearnerStatus | None = None

    @field_validator(
        "learner_code",
        "first_name",
        "last_name",
        "birth_date",
        "sex",
        "grade_level",
        "section",
        "school_year",
        "status",
    )
    @classmethod
    def required_fields_not_null(cls, value: object) -> object:
        # Only runs when the field is sent; a field that is left out stays unchanged.
        if value is None:
            raise ValueError("This field is required.")
        return value


class LearnerList(BaseModel):
    items: list[LearnerRead]
    total: int


class ModuleSummary(BaseModel):
    """Counts and latest status for one module (assessments, IEP, ...).

    ``available`` is false until the stage that builds the module registers it.
    """

    available: bool
    count: int = 0
    latest_status: str | None = None
    latest_at: datetime | None = None


class LearnerSummary(BaseModel):
    learner: LearnerRead
    modules: dict[str, ModuleSummary]


class AssignmentCreate(BaseModel):
    user_id: int
    # Defaults to the learner's current school year.
    school_year: SchoolYear | None = None


class AssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    learner_id: int
    user_id: int
    user_name: str
    school_year: str
    created_at: datetime
