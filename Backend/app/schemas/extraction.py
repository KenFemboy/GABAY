from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.models.extraction import ExtractionMethod, ExtractionStatus, FindingOrigin
from app.schemas.common import strip_required
from app.services.extraction.schema import FindingCategory, FindingDomain

FindingText = Annotated[str, Field(max_length=2000), AfterValidator(strip_required)]


class FindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: FindingCategory
    domain: FindingDomain | None
    text: str
    position: int
    source_page: int | None
    source_start: int | None
    source_end: int | None
    source_quote: str | None
    origin: FindingOrigin
    edited: bool


class VersionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    assessment_id: int
    version_number: int
    method: ExtractionMethod
    status: ExtractionStatus
    based_on_version_id: int | None
    extractor_version: str
    created_by_name: str
    created_at: datetime
    approved_by_name: str | None
    approved_at: datetime | None
    finding_count: int = 0
    is_stale: bool = False


class VersionRead(VersionSummary):
    findings: list[FindingRead]


class VersionList(BaseModel):
    items: list[VersionSummary]


class FindingCreate(BaseModel):
    category: FindingCategory
    domain: FindingDomain | None = None
    text: FindingText


class FindingUpdate(BaseModel):
    category: FindingCategory | None = None
    domain: FindingDomain | None = None
    text: FindingText | None = None


class FindingOrder(BaseModel):
    finding_ids: list[int]


class LearnerFinding(FindingRead):
    """An approved finding, as offered to goal matching."""

    assessment_id: int
    version_id: int
    version_number: int
    stale: bool


class LearnerFindingList(BaseModel):
    items: list[LearnerFinding]
