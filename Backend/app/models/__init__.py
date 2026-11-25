"""Import every model here so Alembic autogenerate sees the full metadata."""

from app.models.assessment import Assessment, AssessmentType, Document, ProcessingStatus
from app.models.ocr import OcrJob, OcrJobStatus, OcrPage, OcrPageSource, OcrPageStatus
from app.models.learner import GradeLevel, Learner, LearnerAssignment, LearnerStatus, Sex
from app.models.user import Role, User, UserStatus

__all__ = [
    "Assessment",
    "AssessmentType",
    "Document",
    "GradeLevel",
    "ProcessingStatus",
    "Learner",
    "LearnerAssignment",
    "LearnerStatus",
    "OcrJob",
    "OcrJobStatus",
    "OcrPage",
    "OcrPageSource",
    "OcrPageStatus",
    "Role",
    "Sex",
    "User",
    "UserStatus",
]
