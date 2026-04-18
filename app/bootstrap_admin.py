"""First-time admin: optional env bootstrap or rely on first /register (see auth routes)."""
import logging
import os

from passlib.context import CryptContext

from .database import SessionLocal
from .models.user import User

logger = logging.getLogger(__name__)

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def ensure_default_admin() -> None:
    """
    If the users table is empty:
    - SCANSCRIBE_DEFAULT_ADMIN_PASSWORD set → create admin (username/email from env or defaults).
    - Else → log hint; first registration via /api/auth/register becomes admin (handled in auth).
    """
    db = SessionLocal()
    try:
        if db.query(User).count() > 0:
            return

        password = (os.getenv("SCANSCRIBE_DEFAULT_ADMIN_PASSWORD") or "").strip()
        if password:
            username = (os.getenv("SCANSCRIBE_DEFAULT_ADMIN_USERNAME") or "admin").strip() or "admin"
            email = (os.getenv("SCANSCRIBE_DEFAULT_ADMIN_EMAIL") or "admin@localhost").strip() or "admin@localhost"
            user = User(
                username=username,
                email=email,
                hashed_password=_pwd.hash(password),
                is_active=True,
                is_admin=True,
            )
            db.add(user)
            db.commit()
            logger.info(
                "Bootstrap admin created (username=%r). Change password after first login.",
                username,
            )
            return

        logger.info(
            "No users yet. Options: (1) set SCANSCRIBE_DEFAULT_ADMIN_PASSWORD [+ "
            "SCANSCRIBE_DEFAULT_ADMIN_USERNAME / SCANSCRIBE_DEFAULT_ADMIN_EMAIL] and restart; "
            "(2) register once — the first account becomes admin."
        )
    finally:
        db.close()
