import re

with open("app/routes/events.py", "r") as f:
    content = f.read()

new_route = """

@router.get("/units/today")
async def get_units_today(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_events_db)
):
    \"\"\"Get distinct UNIT canonical values logged today (for the config UI defaults).\"\"\"
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = db.query(EntityObservation.canonical).filter(
        EntityObservation.label == 'UNIT',
        EntityObservation.ts >= today_start
    ).distinct().all()
    units = [r[0] for r in rows if r[0]]
    units.sort()
    return {"units": units}

"""

if "get_units_today" not in content:
    content = content.replace('@router.get("/monitors", response_model=List[MonitorResponse])', new_route + '\n@router.get("/monitors", response_model=List[MonitorResponse])')
    with open("app/routes/events.py", "w") as f:
        f.write(content)
    print("Added route.")
else:
    print("Route already exists.")
