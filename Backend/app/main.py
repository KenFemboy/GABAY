from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db.session import engine

settings = get_settings()
app = FastAPI(title=settings.app_name, version=settings.app_version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def error_response(code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return error_response("http_error", str(exc.detail), exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return error_response("validation_error", "The request data is invalid.", 422)


@app.get("/api/health")
def health() -> dict:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
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
    }