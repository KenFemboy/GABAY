from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.errors import APIError
from app.db.session import engine
from app.routers import (
    assessments,
    auth,
    evaluations,
    extractions,
    files,
    goals,
    iep,
    ilaw,
    learners,
    matching,
    progress,
    users,
)
from app.services.ocr_service import tesseract_status

settings = get_settings()
app = FastAPI(title=settings.app_name, version=settings.app_version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def error_response(
    code: str,
    message: str,
    status_code: int,
    *,
    details: list[dict] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    error: dict = {"code": code, "message": message}
    if details:
        error["details"] = details
    return JSONResponse(status_code=status_code, content={"error": error}, headers=headers)


@app.exception_handler(APIError)
async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    return error_response(exc.code, exc.message, exc.status_code, details=exc.details, headers=exc.headers)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return error_response("http_error", str(exc.detail), exc.status_code, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    details = []
    for err in exc.errors():
        loc = [str(part) for part in err.get("loc", ()) if part not in ("body", "query", "path")]
        if err.get("type") == "missing":
            message = "This field is required."
        else:
            message = str(err.get("msg", "Invalid value.")).removeprefix("Value error, ")
        details.append({"field": ".".join(loc), "message": message})
    return error_response("validation_error", "The request data is invalid.", 422, details=details)


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(learners.router)
app.include_router(assessments.router)
app.include_router(files.router)
app.include_router(extractions.router)
app.include_router(goals.router)
app.include_router(matching.router)
app.include_router(iep.router)
app.include_router(ilaw.router)
app.include_router(progress.router)
app.include_router(evaluations.router)


@app.get("/api/health")
def health() -> dict:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return {
            "status": "degraded",
            "database": "unavailable",
            "error": {
                "code": "database_unavailable",
                "message": "The API is running, but the database connection is unavailable.",
            },
        }
    return {"status": "ok", "database": "ok"}


@app.get("/api/version")
def version() -> dict:
    return {"name": settings.app_name, "version": settings.app_version}


@app.get("/api/config/status")
def config_status() -> dict:
    return {
        "environment": settings.environment,
        "frontend_origin": settings.frontend_origin,
        "database_configured": bool(settings.database_url),
        "storage_backend": settings.storage_backend,
        **tesseract_status(settings),
        "pgvector": pgvector_version(),
        "evaluation_ai": {
            "enabled": settings.evaluation_ai_enabled,
            "configured": settings.evaluation_ai_configured,
        },
    }


def pgvector_version() -> str | None:
    """Installed pgvector version, or None (not PostgreSQL, not installed, or DB down)."""
    try:
        with engine.connect() as connection:
            if connection.dialect.name != "postgresql":
                return None
            return connection.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            ).scalar()
    except SQLAlchemyError:
        return None
