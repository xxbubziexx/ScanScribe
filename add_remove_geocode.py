import re
with open("app/routes/events.py", "r") as f:
    content = f.read()

new_route = """
@router.post("/events/{event_id}/remove-geocode")
async def remove_geocode(
    event_id: str,
    current_user: User = Depends(get_current_active_user),
    events_db: Session = Depends(get_events_db),
):
    event = events_db.query(Event).filter(Event.event_id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    event.latitude = None
    event.longitude = None
    event.resolved_address = None
    events_db.commit()

    from ..services.websocket import websocket_manager
    websocket_manager.broadcast_sync({
        "type": "event_geocoded",
        "data": {
            "event_id": event_id,
            "monitor_id": event.monitor_id,
            "location": event.location,
            "latitude": None,
            "longitude": None,
            "resolved_address": None,
        }
    })
    return {"ok": True, "message": "Pin removed"}
"""

if "remove-geocode" not in content:
    content = content.replace('@router.post("/events/{event_id}/geocode")', new_route + '\n@router.post("/events/{event_id}/geocode")')
    with open("app/routes/events.py", "w") as f:
        f.write(content)
    print("Added route.")
else:
    print("Route already exists.")
