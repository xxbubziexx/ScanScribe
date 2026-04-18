"""User management routes."""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List

from ..database import get_db
from ..models.user import User
from .auth import get_current_active_user

router = APIRouter(prefix="/api/users", tags=["users"])
logger = logging.getLogger(__name__)


class UserResponse(BaseModel):
    """User response model."""
    id: int
    username: str
    email: str
    is_active: bool
    is_admin: bool
    created_at: str
    
    class Config:
        from_attributes = True


@router.get("/list", response_model=List[UserResponse])
async def list_users(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get list of all users."""
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
            created_at=user.created_at.isoformat() if user.created_at else ""
        )
        for user in users
    ]


@router.post("/{user_id}/promote")
async def promote_user(
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Promote user to admin."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.is_admin = True
    db.commit()
    
    logger.info(f"User {user.username} promoted to admin by {current_user.username}")
    
    return {"message": f"{user.username} is now an admin"}


@router.post("/{user_id}/demote")
async def demote_user(
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
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
    
    return {"message": f"{user.username} is no longer an admin"}


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
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
    
    return {"message": f"User {username} deleted"}


@router.post("/{user_id}/toggle-active")
async def toggle_user_active(
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
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
    
    return {"message": f"User {user.username} {status}", "is_active": user.is_active}
