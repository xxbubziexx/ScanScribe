"""User management routes."""
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.user import User
from .auth import get_current_active_user

router = APIRouter(prefix="/api/users", tags=["users"])
logger = logging.getLogger(__name__)


def _format_iso(dt: Optional[datetime]) -> Optional[str]:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


class UserResponse(BaseModel):
    """User response model."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    is_active: bool
    is_admin: bool
    created_at: str
    last_seen_at: Optional[str] = None


class UserActionResponse(BaseModel):
    """Generic action response model for user operations."""
    model_config = ConfigDict(from_attributes=True)

    message: str
    is_active: Optional[bool] = None


@router.get("/list", response_model=List[UserResponse])
def list_users(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> List[UserResponse]:
    """Get list of all users. Runs in threadpool to prevent blocking the event loop."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    users = db.query(User).all()
    
    return [
        UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            is_active=user.is_active,
            is_admin=user.is_admin,
            created_at=_format_iso(user.created_at) or "",
            last_seen_at=_format_iso(user.last_seen_at),
        )
        for user in users
    ]




@router.post("/{user_id}/promote", response_model=UserActionResponse)
def promote_user(
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> UserActionResponse:
    """Promote user to admin."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.is_admin = True
    db.commit()
    
    logger.info(f"User {user.username} promoted to admin by {current_user.username}")
    
    return UserActionResponse(message=f"{user.username} is now an admin")


@router.post("/{user_id}/demote", response_model=UserActionResponse)
def demote_user(
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> UserActionResponse:
    """Demote user from admin."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Can't demote yourself if you're the last admin
    admin_count = db.query(User).filter(User.is_admin == True).count()
    if user.id == current_user.id and admin_count == 1:
        raise HTTPException(status_code=400, detail="Cannot demote the last admin")
    
    user.is_admin = False
    db.commit()
    
    logger.info(f"User {user.username} demoted from admin by {current_user.username}")
    
    return UserActionResponse(message=f"{user.username} is no longer an admin")


@router.delete("/{user_id}", response_model=UserActionResponse)
def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> UserActionResponse:
    """Delete a user."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Can't delete yourself
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    
    # Can't delete the last admin
    if user.is_admin:
        admin_count = db.query(User).filter(User.is_admin == True).count()
        if admin_count == 1:
            raise HTTPException(status_code=400, detail="Cannot delete the last admin")
    
    username = user.username
    db.delete(user)
    db.commit()
    
    logger.info(f"User {username} deleted by {current_user.username}")
    
    return UserActionResponse(message=f"User {username} deleted")


@router.post("/{user_id}/toggle-active", response_model=UserActionResponse)
def toggle_user_active(
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> UserActionResponse:
    """Toggle user active status."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Can't deactivate yourself
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
    
    user.is_active = not user.is_active
    db.commit()
    
    status = "activated" if user.is_active else "deactivated"
    logger.info(f"User {user.username} {status} by {current_user.username}")
    
    return UserActionResponse(message=f"User {user.username} {status}", is_active=user.is_active)

