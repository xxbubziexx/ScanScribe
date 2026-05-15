"""Main FastAPI application."""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
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

# Templates and static files
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount("/audio_storage", StaticFiles(directory=str(settings.output_dir)), name="audio_storage")

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


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "ingest_dir": str(settings.ingest_dir),
        "model": settings.model_name
    }


@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    """Root endpoint - redirect to login."""
    return RedirectResponse(url="/login")


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    """Login page."""
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    """Registration page."""
    return templates.TemplateResponse("register.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    """Main dashboard (protected route)."""
    # TODO: Add authentication middleware
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    """Settings page."""
    # TODO: Add authentication middleware
    return templates.TemplateResponse("settings.html", {"request": request})


@app.get("/logs", response_class=HTMLResponse)
def logs_page(request: Request):
    """Logs page."""
    # TODO: Add authentication middleware
    return templates.TemplateResponse("logs.html", {"request": request})


@app.get("/users", response_class=HTMLResponse)
def users_page(request: Request):
    """Users management page."""
    return templates.TemplateResponse("users.html", {"request": request})


@app.get("/insights", response_class=HTMLResponse)
def insights_page(request: Request):
    """Insights and analytics page."""
    return templates.TemplateResponse("insights.html", {"request": request})


@app.get("/events", response_class=HTMLResponse)
def events_page(request: Request):
    """Events pipeline: events list and debug."""
    return templates.TemplateResponse("events.html", {"request": request})


@app.get("/events/{event_id}", response_class=HTMLResponse)
def event_detail_page(request: Request, event_id: str):
    """Event detail: header and linked transcripts."""
    return templates.TemplateResponse("event_detail.html", {"request": request, "event_id": event_id})


