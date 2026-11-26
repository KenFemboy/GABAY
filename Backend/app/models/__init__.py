"""Import every model here so Alembic autogenerate sees the full metadata."""

from app.models.assessment import Assessment, AssessmentType, Document, ProcessingStatus
from app.models.extraction import (
    ExtractionFinding,
    ExtractionMethod,
    ExtractionStatus,
    ExtractionVersion,
    FindingOrigin,
)
from app.models.goal import (
    Goal,
    GoalDomain,
    GoalEmbedding,
    GoalSkill,
    GoalStatus,
    GoalUsage,
    GoalVersion,
)
from app.models.matching import (
    GoalRecommendation,
    MatchingRun,
    NeedEmbedding,
    RecommendationSource,
    RecommendationStatus,
)
from app.models.ocr import OcrJob, OcrJobStatus, OcrPage, OcrPageSource, OcrPageStatus
from app.models.learner import GradeLevel, Learner, LearnerAssignment, LearnerStatus, Sex
from app.models.user import Role, User, UserStatus

__all__ = [
    "Assessment",
    "AssessmentType",
    "Document",
    "ExtractionFinding",
    "ExtractionMethod",
    "ExtractionStatus",
    "ExtractionVersion",
    "FindingOrigin",
    "Goal",
    "GoalDomain",
    "GoalEmbedding",
    "GoalRecommendation",
    "MatchingRun",
    "NeedEmbedding",
    "RecommendationSource",
    "RecommendationStatus",
    "GoalSkill",
    "GoalStatus",
    "GoalUsage",
    "GoalVersion",
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
