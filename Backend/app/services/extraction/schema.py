"""The extraction schema: what a finding is.

This is also the output contract for any future extractor (for example an
AI extractor working on de-identified text): it must return an
``ExtractionResult`` whose findings point back into the page texts.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class FindingCategory(StrEnum):
    DIAGNOSIS = "diagnosis"  # only from an explicit label in the report
    STRENGTH = "strength"
    NEED = "need"
    PRESENT_LEVEL = "present_level"  # present level of performance in one domain
    RECOMMENDATION = "recommendation"


class FindingDomain(StrEnum):
    READING = "reading"
    WRITING = "writing"
    MATHEMATICS = "mathematics"
    BEHAVIOR_SOCIAL = "behavior_social"
    COMMUNICATION = "communication"
    MOTOR = "motor"
    SELF_HELP = "self_help"
    COGNITIVE = "cognitive"
    OTHER = "other"


class SourceRef(BaseModel):
    """Where a finding came from: character offsets into one page's text."""

    page: int = Field(ge=1)
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    quote: str = Field(max_length=500)


class FindingDraft(BaseModel):
    category: FindingCategory
    domain: FindingDomain | None = None
    text: str = Field(min_length=1, max_length=2000)
    source: SourceRef | None = None


class ExtractionResult(BaseModel):
    extractor: str  # e.g. "rules-1"
    findings: list[FindingDraft]


class PageText(BaseModel):
    page_number: int
    text: str
