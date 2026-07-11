"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from pathlib import Path
import time

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.api.routes import router as api_router
from app.api.file_routes import router as file_router
from app.api.tool_routes import router as tool_router
from app.api.checklist_routes import router as checklist_router
from app.api.ai_routes import router as ai_router
from app.api.auth_routes import router as auth_router
from app.api.payment_routes import router as payment_router
from app import storage
from app.logging_config import logger
from app.database import engine, init_db
from app.monitoring import request_metrics


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
    version="5.4.1",
    lifespan=lifespan,
)

# Mount static files and templates
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

# Include API routes
app.include_router(api_router, prefix="/api")
app.include_router(file_router, prefix="/api")
app.include_router(tool_router, prefix="/api")
app.include_router(checklist_router, prefix="/api")
app.include_router(ai_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(payment_router, prefix="/api")


@app.middleware("http")
async def monitoring_middleware(request: Request, call_next):
    """Record coarse request counts, latency, and server errors."""
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000
        route = request.scope.get("route")
        path = getattr(route, "path", request.url.path)
        request_metrics.record(request.method, path, status_code, elapsed_ms)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Add baseline browser security headers without breaking the current SPA."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data: blob:; "
        "font-src 'self' data: https://cdn.jsdelivr.net; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'; "
        "form-action 'self'",
    )
    return response


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
    resp = templates.TemplateResponse(request=request, name="index.html")
    # Never cache the shell HTML — it references versioned static assets and
    # a stale cached copy silently pins users to old (possibly broken) JS.
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@app.get("/healthz")
async def healthz():
    """Liveness probe: process is running."""
    return {"status": "ok", "service": "scholarlint", "version": app.version}


@app.get("/readyz")
async def readyz():
    """Readiness probe with deployment-risk checks.

    This intentionally returns sanitized booleans/status strings only. Never
    include secret values or internal LLM endpoints in health responses.
    """
    from sqlalchemy import text
    from app import secrets_manager as sm

    checks: dict[str, dict] = {}

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = {"ok": True}
    except Exception as exc:
        checks["database"] = {"ok": False, "detail": type(exc).__name__}

    crypto_ok = sm.is_available()
    checks["crypto"] = {
        "ok": crypto_ok,
        "detail": "encrypted store available" if crypto_ok else "encrypted store unavailable",
    }

    checks["llm"] = {
        "ok": bool(settings.llm_api_key and settings.llm_base_url and settings.llm_model),
        "model_configured": bool(settings.llm_model),
    }

    production = settings.app_env in {"prod", "production"}
    checks["payment"] = {
        "ok": not (production and settings.payment_sandbox),
        "sandbox": settings.payment_sandbox,
        "detail": "sandbox must be disabled in production" if production and settings.payment_sandbox else "ok",
    }

    checks["storage"] = {
        "ok": settings.upload_dir.exists() and settings.data_dir.exists(),
        "upload_dir": settings.upload_dir.exists(),
        "data_dir": settings.data_dir.exists(),
    }

    ready = all(item.get("ok") for item in checks.values())
    return {"status": "ready" if ready else "degraded", "environment": settings.app_env, "checks": checks}


@app.get("/metrics")
async def metrics():
    """Operational metrics for uptime, latency, and server error rate."""
    return request_metrics.snapshot(service="scholarlint", version=app.version)


@app.get("/report/{job_id}", response_class=HTMLResponse)
async def report_page(request: Request, job_id: str):
    """Render the report page for a completed check."""
    return templates.TemplateResponse(request=request, name="report.html", context={"job_id": job_id})


# Ensure upload directory exists
settings.upload_dir.mkdir(exist_ok=True)
