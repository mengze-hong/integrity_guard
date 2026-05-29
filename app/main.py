"""FastAPI application entry point."""

import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.config import settings
from app.api.routes import router as api_router
from app.api.auth_routes import router as auth_router
from app.api.payment_routes import router as payment_router
from app import storage
from app.logging_config import logger
from app.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB, clean expired jobs. Shutdown: no-op."""
    init_db()
    logger.info("Database initialized")
    removed = storage.cleanup_expired()
    if removed:
        logger.info(f"Cleaned up {removed} expired job(s)")
    yield


app = FastAPI(
    title="ScholarLint",
    description="投稿通 — Academic paper pre-submission integrity checker",
    version="5.3.18",
    lifespan=lifespan,
)

# Mount static files and templates
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

# Include API routes
app.include_router(api_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(payment_router, prefix="/api")


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions and return a clean JSON error (secrets redacted)."""
    from app.secrets_manager import redact

    logger.error(f"Unhandled exception: {redact(str(exc))}")
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误，请稍后重试。", "error": redact(str(exc))[:200]},
    )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the upload page."""
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/report/{job_id}", response_class=HTMLResponse)
async def report_page(request: Request, job_id: str):
    """Render the report page for a completed check."""
    return templates.TemplateResponse(request=request, name="report.html", context={"job_id": job_id})


# Ensure upload directory exists
settings.upload_dir.mkdir(exist_ok=True)
