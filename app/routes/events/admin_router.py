"""Events administration, debug, and model status sub-router."""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...config import get_settings
from ...database import get_events_db
from ...models.event import SystemSetting
from ...models.user import User
from ...services.events_debug import clear_all as clear_debug_all, get_recent as get_debug_recent
from ...services.events_router_engine import OpenRouterRateLimitManager
from ...services.ner_service import ENTITY_LABELS, is_loaded
from ..auth import get_current_active_user, get_current_admin_user

router = APIRouter()


class GlobalRulesUpdate(BaseModel):
    global_rules: str


@router.get("/ner-labels")
async def ner_labels(
    current_user: User = Depends(get_current_active_user),
):
    """Supported NER labels for Start event by label."""
    return {"labels": sorted(ENTITY_LABELS)}


@router.get("/debug")
async def events_debug(
    limit: Optional[int] = Query(80, ge=1, le=200),
    current_user: User = Depends(get_current_admin_user),
):
    """Recent NER pipeline debug entries (newest first). In-memory only."""
    return get_debug_recent(limit)


@router.delete("/debug")
async def clear_events_debug(
    current_user: User = Depends(get_current_admin_user),
):
    """Clear all NER pipeline debug entries."""
    removed = clear_debug_all()
    return {"ok": True, "removed": removed}


@router.get("/llm-status")
async def events_llm_status(
    current_user: User = Depends(get_current_active_user),
):
    """NER model status for Events pipeline."""
    settings = get_settings()
    cfg = getattr(settings.config, "events_pipeline", None)
    if not cfg or not cfg.enabled or not cfg.ner_model_path:
        return {
            "enabled": False,
            "ner_model_path": "",
            "status": "disabled",
            "message": "Events pipeline disabled",
        }
    if is_loaded():
        return {"enabled": True, "ner_model_path": cfg.ner_model_path, "status": "ok"}
    return {
        "enabled": True,
        "ner_model_path": cfg.ner_model_path,
        "status": "unreachable",
        "message": "NER model not loaded",
    }


@router.get("/global-rules")
async def get_global_rules_endpoint(
    current_user: User = Depends(get_current_active_user),
    events_db: Session = Depends(get_events_db),
):
    """Retrieve global system prompt rules (checking DB SystemSetting first, falling back to config.yml)."""
    setting = (
        events_db.query(SystemSetting)
        .filter(SystemSetting.key == "global_prompt_rules")
        .first()
    )
    if setting and setting.value is not None:
        return {"global_rules": setting.value}

    settings = get_settings()
    cfg = getattr(settings.config, "events_pipeline", None)
    rules = getattr(cfg, "global_prompt_rules", "") if cfg else ""
    return {"global_rules": rules or ""}


@router.post("/global-rules")
async def update_global_rules_endpoint(
    payload: GlobalRulesUpdate,
    current_user: User = Depends(get_current_admin_user),
    events_db: Session = Depends(get_events_db),
):
    """Update global system prompt rules in DB SystemSetting and sync to in-memory config."""
    cleaned_rules = payload.global_rules.strip()
    setting = (
        events_db.query(SystemSetting)
        .filter(SystemSetting.key == "global_prompt_rules")
        .first()
    )
    if not setting:
        setting = SystemSetting(key="global_prompt_rules", value=cleaned_rules)
        events_db.add(setting)
    else:
        setting.value = cleaned_rules
    events_db.commit()

    settings = get_settings()
    if getattr(settings.config, "events_pipeline", None):
        settings.config.events_pipeline.global_prompt_rules = cleaned_rules

    return {"ok": True, "global_rules": cleaned_rules}


@router.get("/rate-limit-status")
async def get_rate_limit_status(
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Retrieve current OpenRouter rate limit status and remaining cooldown timer."""
    return OpenRouterRateLimitManager.get_status()


@router.post("/rate-limit-status/reset")
async def reset_rate_limit_status(
    current_user: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Reset the OpenRouter rate limit cooldown manually in memory and DB (admin only)."""
    OpenRouterRateLimitManager.reset()
    return {"ok": True, "message": "Rate limit cooldown reset successfully"}
