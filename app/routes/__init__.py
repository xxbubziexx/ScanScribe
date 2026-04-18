"""API routes."""
from .auth import router as auth_router
from .settings import router as settings_router
from .logs import router as logs_router
from .maintenance import router as maintenance_router
from .watcher import router as watcher_router
from .upload import router as upload_router
from .users import router as users_router
from .transcriptions import router as transcriptions_router

__all__ = ["auth_router", "settings_router", "logs_router", "maintenance_router", "watcher_router", "upload_router", "users_router", "transcriptions_router"]
