"""First-run state check: no credentials are seeded, the first registration claims admin."""
import logging

from .database import SessionLocal
from .models.user import User

logger = logging.getLogger(__name__)


def ensure_default_admin() -> None:
    """Report whether the install has been claimed yet.

    Nothing is created here. A fresh database is onboarded through the registration
    endpoint, which grants administrator rights to the first account and then closes
    registration to anonymous callers.

    This used to create an account from SCANSCRIBE_DEFAULT_ADMIN_* environment
    variables, defaulting to admin/admin. That meant every install shipped a known
    password and the first-run path never ran, because a user always already existed by
    the time anyone could register.
    """
    db = SessionLocal()
    try:
        user_count = db.query(User).count()
    finally:
        db.close()

    if user_count == 0:
        logger.warning(
            "No user accounts exist yet. Open the web UI and register the first account; "
            "it is granted administrator privileges automatically. Registration closes to "
            "anonymous users once that account exists."
        )
    else:
        logger.debug("User accounts present (%d); first-run onboarding already completed.", user_count)
