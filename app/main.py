"""Main FastAPI application."""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .config import get_settings, init_directories
from .database import init_db
from .bootstrap_admin import ensure_default_admin
from .routes import auth_router, settings_router, logs_router, maintenance_router, watcher_router, upload_router, users_router, transcriptions_router
from .routes.insights import router as insights_router
from .routes.events import router as events_router
from .services.watcher import get_watcher_service
from .services.queue_processor import get_processor
from .services.summaries_auto import start_auto_summary_worker, stop_auto_summary_worker
from .logging_config import setup_logging

# Configure logging with custom handlers
setup_logging(app_name="scanscribe", level="INFO")
logger = logging.getLogger(__name__)

# Initialize settings and directories
settings = get_settings()
init_directories()

# Get service instances
watcher_service = get_watcher_service()
queue_processor = get_processor()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown logic."""
    from .logging_config import WebSocketHandler

    try:
        loop = asyncio.get_running_loop()
        WebSocketHandler.set_main_loop(loop)

        init_db()
        logger.info("✅ Database initialized")
        ensure_default_admin()
        logger.info("✅ Directories initialized")
        logger.info(f"📁 Ingest: {settings.ingest_dir}")
        logger.info(f"📁 Output: {settings.output_dir}")
        logger.info(f"📁 Logs: {settings.log_dir}")

        await queue_processor.start()
        logger.info("✅ Queue processor started")

        from .services.events_worker import ensure_ner_model_loaded, start_event_cleanup_worker
        if ensure_ner_model_loaded():
            logger.info("✅ NER model loaded for events pipeline")
        elif getattr(settings.config, "events_pipeline", None) and settings.config.events_pipeline.enabled:
            logger.warning("⚠️ Events pipeline enabled but NER model failed to load")
        start_event_cleanup_worker()
        logger.info("✅ Events cleanup worker started")

        await watcher_service.start()
        logger.info("✅ File watcher started")

        await start_auto_summary_worker()
        logger.info("✅ Auto summaries worker configured")

        logger.info("🚀 ScanScribe is ready!")
    except Exception as e:
        logger.exception("Startup failed: %s", e)
        raise

    yield

    await queue_processor.stop()
    await watcher_service.stop()
    await stop_auto_summary_worker()
    logger.info("🛑 ScanScribe shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="ScanScribe",
    description="Audio transcription service with Whisper AI",
    version=__version__,
    lifespan=lifespan,
)

# CORS middleware — no credentials needed (Bearer token auth, not cookies)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
app.mount("/audio_storage", StaticFiles(directory=str(settings.output_dir)), name="audio_storage")

# React SPA (Vite `base: '/app/'`, see app/frontend/vite.config.ts). Without these routes,
# a refresh on e.g. /app/login hits FastAPI and returns 404 — only client-side routing worked.
_FRONTEND_DIST = (BASE_DIR / "frontend" / "dist").resolve()


def _spa_index() -> FileResponse:
    index = _FRONTEND_DIST / "index.html"
    if not index.is_file():
        raise HTTPException(
            status_code=503,
            detail="React UI not built. From repo root: cd app/frontend && npm ci && npm run build",
        )
    return FileResponse(index)


def _spa_file_or_shell(full_path: str) -> FileResponse:
    """Serve real files under dist (assets/*.js, etc.) or index.html for client routes."""
    if ".." in full_path.split("/"):
        raise HTTPException(status_code=404, detail="Not found")
    base = _FRONTEND_DIST
    try:
        candidate = (base / full_path).resolve()
    except OSError:
        return _spa_index()
    try:
        candidate.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found") from None
    if candidate.is_file():
        return FileResponse(candidate)
    return _spa_index()


# Include routers
app.include_router(auth_router)
app.include_router(settings_router)
app.include_router(logs_router)
app.include_router(maintenance_router)
app.include_router(watcher_router)
app.include_router(upload_router)
app.include_router(users_router)
app.include_router(transcriptions_router)
app.include_router(insights_router)
app.include_router(events_router)


@app.get("/span-store", include_in_schema=False)
def compat_span_store_api(request: Request):
    """Some older UI builds called GET /span-store instead of /api/events/span-store."""
    dest = "/api/events/span-store"
    if request.url.query:
        dest = f"{dest}?{request.url.query}"
    return RedirectResponse(url=dest, status_code=307)


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "ingest_dir": str(settings.ingest_dir),
        "model": settings.model_name
    }


def _redirect_to_app(path: str) -> RedirectResponse:
    """307 so method/body are preserved if ever used for non-GET (we use GET-only legacy URLs)."""
    return RedirectResponse(url=f"/app{path}", status_code=307)


@app.get("/", include_in_schema=False)
def root():
    """Send users to the React shell."""
    return RedirectResponse(url="/app/", status_code=307)


@app.get("/login", include_in_schema=False)
def legacy_login_redirect():
    return _redirect_to_app("/login")


@app.get("/register", include_in_schema=False)
def legacy_register_redirect():
    return _redirect_to_app("/register")


@app.get("/dashboard", include_in_schema=False)
def legacy_dashboard_redirect():
    return _redirect_to_app("/")


@app.get("/insights", include_in_schema=False)
def legacy_insights_redirect():
    return _redirect_to_app("/insights")


@app.get("/logs", include_in_schema=False)
def legacy_logs_redirect():
    return _redirect_to_app("/logs")


@app.get("/users", include_in_schema=False)
def legacy_users_redirect():
    return _redirect_to_app("/users")


@app.get("/settings", include_in_schema=False)
def legacy_settings_redirect():
    return _redirect_to_app("/settings")


@app.get("/events", include_in_schema=False)
def legacy_events_redirect():
    return _redirect_to_app("/events")


# React Events hub sub-routes (must not be treated as public event_id hex strings).
_EVENTS_SPA_SUBPATHS = frozenset({"monitors", "debug", "span-store"})


@app.get("/events/{event_id}", include_in_schema=False)
def legacy_event_detail_redirect(event_id: str):
    """Legacy URLs without /app prefix → React shell (preserve sub-routes)."""
    if event_id in _EVENTS_SPA_SUBPATHS:
        return _redirect_to_app(f"/events/{event_id}")
    return _redirect_to_app("/events")


@app.get("/app")
def react_app_shell():
    return _spa_index()


@app.get("/app/")
def react_app_shell_slash():
    return _spa_index()


@app.get("/app/{full_path:path}")
def react_app_spa(full_path: str):
    """History fallback: /app/login, /app/dashboard, … → index.html; real paths → files in dist."""
    return _spa_file_or_shell(full_path)
