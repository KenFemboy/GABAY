from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET_KEY = "dev-only-insecure-secret-change-me"


class Settings(BaseSettings):
    app_name: str = "GABAY API"
    app_version: str = "0.1.0"
    environment: str = "development"
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/gabay",
        validation_alias="DATABASE_URL",
    )
    frontend_origin: str = Field(
        default="http://localhost:5173",
        validation_alias="FRONTEND_ORIGIN",
    )

    jwt_secret_key: str = Field(default=DEV_SECRET_KEY, validation_alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", validation_alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(
        default=60, validation_alias="ACCESS_TOKEN_EXPIRE_MINUTES"
    )

    # Document storage. "local" writes to disk (development/tests, no cloud keys
    # needed); "supabase" uses a private Supabase Storage bucket.
    storage_backend: Literal["local", "supabase"] = Field(
        default="local", validation_alias="STORAGE_BACKEND"
    )
    storage_local_dir: str = Field(default="storage", validation_alias="STORAGE_LOCAL_DIR")
    supabase_url: str = Field(default="", validation_alias="SUPABASE_URL")
    # Secret: backend only, never sent to the frontend.
    supabase_service_role_key: str = Field(
        default="", validation_alias="SUPABASE_SERVICE_ROLE_KEY"
    )
    supabase_bucket: str = Field(default="gabay-documents", validation_alias="SUPABASE_BUCKET")
    max_upload_mb: int = Field(default=15, ge=1, le=50, validation_alias="MAX_UPLOAD_MB")
    signed_url_ttl_seconds: int = Field(
        default=60, ge=10, le=3600, validation_alias="SIGNED_URL_TTL_SECONDS"
    )
    # Base URL of this API as the browser sees it; used for local-storage signed URLs.
    public_api_url: str = Field(default="http://localhost:8000", validation_alias="PUBLIC_API_URL")

    # OCR (Stage 5). Run the worker with: python -m app.workers.ocr_worker
    # Blank TESSERACT_CMD means "find tesseract on PATH".
    tesseract_cmd: str = Field(default="", validation_alias="TESSERACT_CMD")
    ocr_languages: str = Field(default="eng+fil", validation_alias="OCR_LANGUAGES")
    ocr_dpi: int = Field(default=300, ge=72, le=600, validation_alias="OCR_DPI")
    ocr_max_pages: int = Field(default=50, ge=1, le=500, validation_alias="OCR_MAX_PAGES")
    # Pages below this mean word confidence (0-100) send the assessment to Needs Review.
    ocr_review_confidence: float = Field(
        default=70, ge=0, le=100, validation_alias="OCR_REVIEW_CONFIDENCE"
    )
    # A PDF page with at least this many text-layer characters is not OCR'd.
    ocr_min_text_layer_chars: int = Field(
        default=20, ge=1, validation_alias="OCR_MIN_TEXT_LAYER_CHARS"
    )
    ocr_page_timeout_seconds: int = Field(
        default=120, ge=5, validation_alias="OCR_PAGE_TIMEOUT_SECONDS"
    )
    ocr_worker_poll_seconds: float = Field(
        default=2, gt=0, validation_alias="OCR_WORKER_POLL_SECONDS"
    )
    ocr_job_timeout_minutes: int = Field(
        default=30, ge=1, validation_alias="OCR_JOB_TIMEOUT_MINUTES"
    )
    ocr_max_attempts: int = Field(default=2, ge=1, le=10, validation_alias="OCR_MAX_ATTEMPTS")

    # Information extraction (Stage 6). Only rule-based extraction exists; this
    # placeholder is for a later AI extractor that works on de-identified text.
    extraction_ai_enabled: bool = Field(default=False, validation_alias="EXTRACTION_AI_ENABLED")

    # Goal bank embeddings (Stage 7): local fastembed model, no external API.
    embedding_model: str = Field(
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        validation_alias="EMBEDDING_MODEL",
    )
    embedding_cache_dir: str = Field(default=".models", validation_alias="EMBEDDING_CACHE_DIR")

    # Printed on generated documents such as the IEP (Stage 9).
    school_name: str = Field(default="Sample School", validation_alias="SCHOOL_NAME")

    # Goal matching (Stage 8).
    match_min_score: float = Field(default=0.35, ge=0, le=1, validation_alias="MATCH_MIN_SCORE")
    match_top_k: int = Field(default=5, ge=1, le=20, validation_alias="MATCH_TOP_K")

    # ILAW alignment (Stage 10): suggested IEP goals per activity entry.
    ilaw_top_k: int = Field(default=3, ge=1, le=10, validation_alias="ILAW_TOP_K")
    ilaw_min_score: float = Field(default=0.35, ge=0, le=1, validation_alias="ILAW_MIN_SCORE")

    # Year-end evaluation (Stage 12). AI drafting is OFF unless enabled AND a key and
    # model are set. The key is backend-only and never logged or returned.
    evaluation_ai_enabled: bool = Field(default=False, validation_alias="EVALUATION_AI_ENABLED")
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    openai_model: str = Field(default="", validation_alias="OPENAI_MODEL")
    openai_timeout_seconds: float = Field(default=60, gt=0, le=600, validation_alias="OPENAI_TIMEOUT_SECONDS")

    @property
    def evaluation_ai_configured(self) -> bool:
        return bool(self.openai_api_key and self.openai_model)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def require_real_secret_outside_development(self) -> "Settings":
        if self.environment not in {"development", "test"}:
            if self.jwt_secret_key == DEV_SECRET_KEY or len(self.jwt_secret_key) < 32:
                raise ValueError(
                    "JWT_SECRET_KEY must be set to a random value of at least 32 "
                    "characters outside development."
                )
        if self.storage_backend == "supabase" and not (
            self.supabase_url and self.supabase_service_role_key
        ):
            raise ValueError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required when "
                "STORAGE_BACKEND=supabase."
            )
        return self

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
