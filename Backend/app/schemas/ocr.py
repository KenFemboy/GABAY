from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models.ocr import OcrJobStatus, OcrPageSource, OcrPageStatus
from app.services.ocr_job_service import MAX_REVIEWED_CHARS


class OcrJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: OcrJobStatus
    attempts: int
    error_code: str | None
    error_message: str | None
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class OcrPageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    page_number: int
    source: OcrPageSource
    status: OcrPageStatus
    confidence: float | None
    error_message: str | None
    raw_text: str
    reviewed_text: str | None
    reviewed_by_name: str | None
    reviewed_at: datetime | None


class OcrSummary(BaseModel):
    page_count: int
    failed_pages: int
    low_confidence_pages: int
    reviewed_pages: int
    mean_confidence: float | None
    review_confidence: float


class OcrResultRead(BaseModel):
    job: OcrJobRead | None
    pages: list[OcrPageRead]
    summary: OcrSummary


class OcrPageUpdate(BaseModel):
    # null reverts the page to the raw OCR text.
    reviewed_text: Annotated[str, Field(max_length=MAX_REVIEWED_CHARS)] | None
