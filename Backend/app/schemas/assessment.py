from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, computed_field

from app.models.assessment import AssessmentType, ProcessingStatus
from app.schemas.common import strip_optional, strip_required
from app.services.assessment_status import next_manual_statuses


def not_in_future(value: date) -> date:
    if value > date.today():
        raise ValueError("Assessment date cannot be in the future.")
    return value


class AssessmentCreate(BaseModel):
    learner_id: int
    assessment_type: AssessmentType
    assessment_date: Annotated[date, AfterValidator(not_in_future)]
    assessor: Annotated[str, Field(max_length=150), AfterValidator(strip_required)]
    notes: Annotated[
        Annotated[str, Field(max_length=5000)] | None, BeforeValidator(strip_optional)
    ] = None


class DocumentRead(BaseModel):
    """Safe document metadata. The storage key and checksum are never returned."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    original_filename: str
    mime_type: str
    file_size: int
    uploaded_by_name: str
    uploaded_at: datetime


class AssessmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    learner_id: int
    assessment_type: AssessmentType
    assessment_date: date
    assessor: str
    notes: str | None
    processing_status: ProcessingStatus
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    document: DocumentRead | None

    @computed_field
    @property
    def next_statuses(self) -> list[ProcessingStatus]:
        """Statuses a Coordinator may move this assessment to next."""
        return next_manual_statuses(self.processing_status)


class AssessmentStatusUpdate(BaseModel):
    status: ProcessingStatus


class AssessmentList(BaseModel):
    items: list[AssessmentRead]
    total: int


class SignedUrlRead(BaseModel):
    url: str
    expires_in: int
