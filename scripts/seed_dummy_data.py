"""Seed realistic scanner radio transmission data and NER entity observations for testing and demos."""
import argparse
from datetime import datetime, date, time, timedelta, timezone
import json
import random
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from app.models.log_entry import LogEntry
from app.models.event import Monitor, SpanStore, EntityObservation, Event, EventTranscriptLink


SAMPLE_TALKGROUPS = [
    ("St. Francois Central Dispatch Law 1", 1),
    ("St. Francois Central Dispatch Fire Main 1", 2),
    ('7603"Washington County: Law 1: Sheriff"', 3),
    ('5008"Iron County Law"', 4),
    ("Central Dispatch Law 3", 1),
    ("St. Francois Central Dispatch EMS 1", 2),
]

DISPATCH_TEMPLATES = [
    # Traffic stops
    {
        "transcript": "Central, Unit 112, 10-38 traffic stop on Highway 67 northbound near Maple Street, Missouri tag Adam King 4 9 2.",
        "units": ["Unit 112"],
        "evt_type": "Traffic Stop",
        "loc": "Highway 67",
        "address": "Highway 67 & Maple St",
        "status": "On Scene",
        "dur": 7.8,
    },
    {
        "transcript": "112 Central, driver checks out 10-4, clear from the stop on Highway 67, back in service.",
        "units": ["Unit 112"],
        "evt_type": None,
        "loc": "Highway 67",
        "address": None,
        "status": "In Service",
        "dur": 5.4,
    },
    {
        "transcript": "Car 204, show me 10-38 on Karsch Blvd near Walton Dr with a red pickup.",
        "units": ["Car 204"],
        "evt_type": "Traffic Stop",
        "loc": "Karsch Blvd",
        "address": "Karsch Blvd & Walton Dr",
        "status": "On Scene",
        "dur": 6.2,
    },
    # Structure Fires
    {
        "transcript": "All stations, structure fire reported at 1155 Walton Dr, smoke showing from single family dwelling. Engine 9, Truck 3, Battalion 1 respond.",
        "units": ["Engine 9", "Truck 3", "Battalion 1"],
        "evt_type": "Structure Fire",
        "loc": "Walton Dr",
        "address": "1155 Walton Dr",
        "status": "En Route",
        "dur": 12.4,
    },
    {
        "transcript": "Engine 9 is on scene 1155 Walton Dr, two story residential with working fire on division one. Establishing Walton command.",
        "units": ["Engine 9"],
        "evt_type": "Structure Fire",
        "loc": "Walton Dr",
        "address": "1155 Walton Dr",
        "status": "On Scene",
        "dur": 10.1,
    },
    {
        "transcript": "Battalion 1 on scene assuming Walton command. Primary search underway. Truck 3 vent the roof.",
        "units": ["Battalion 1", "Truck 3"],
        "evt_type": "Structure Fire",
        "loc": "Walton Dr",
        "address": "1155 Walton Dr",
        "status": "On Scene",
        "dur": 8.7,
    },
    # Motor Vehicle Accidents
    {
        "transcript": "Central Dispatch, 10-50 J2 two-vehicle accident with entrapment on Highway 32 near Weber Road. Dispatched Medic 4, Rescue 7.",
        "units": ["Medic 4", "Rescue 7"],
        "evt_type": "10-50 Vehicle Accident",
        "loc": "Highway 32",
        "address": "Highway 32 & Weber Rd",
        "status": "En Route",
        "dur": 9.8,
    },
    {
        "transcript": "Medic 4 on scene Highway 32, one patient extricated, preparing for transport to Parkland Hospital.",
        "units": ["Medic 4"],
        "evt_type": "10-50 Vehicle Accident",
        "loc": "Highway 32",
        "address": None,
        "status": "Transporting",
        "dur": 8.3,
    },
    # Medical emergencies
    {
        "transcript": "Medic 7 responding 422 West Maple Street for a 68-year-old male with severe chest pain and shortness of breath.",
        "units": ["Medic 7"],
        "evt_type": "Chest Pain / Medical",
        "loc": "West Maple Street",
        "address": "422 West Maple Street",
        "status": "En Route",
        "dur": 8.9,
    },
    {
        "transcript": "Medic 7 on scene West Maple Street.",
        "units": ["Medic 7"],
        "evt_type": "Medical Emergency",
        "loc": "West Maple Street",
        "address": "422 West Maple Street",
        "status": "On Scene",
        "dur": 4.1,
    },
    # Commercial fire alarm
    {
        "transcript": "Engine 14, commercial waterflow alarm sounding at Oak Ridge Crossing, 900 East Columbia.",
        "units": ["Engine 14"],
        "evt_type": "Commercial Fire Alarm",
        "loc": "Oak Ridge Crossing",
        "address": "900 East Columbia",
        "status": "En Route",
        "dur": 7.2,
    },
    {
        "transcript": "Engine 14 on scene Oak Ridge Crossing, two-story commercial, nothing showing from exterior, investigating.",
        "units": ["Engine 14"],
        "evt_type": "Commercial Fire Alarm",
        "loc": "Oak Ridge Crossing",
        "address": "900 East Columbia",
        "status": "On Scene",
        "dur": 6.8,
    },
    # Officer status / check-ins
    {
        "transcript": "Deputy 8131, show me 10-8 available countywide.",
        "units": ["Deputy 8131"],
        "evt_type": None,
        "loc": None,
        "address": None,
        "status": "In Service",
        "dur": 4.2,
    },
    {
        "transcript": "Car 115, 10-6 at the Sheriff's Office writing reports.",
        "units": ["Car 115"],
        "evt_type": None,
        "loc": "Sheriff's Office",
        "address": None,
        "status": "Available",
        "dur": 4.5,
    },
    {
        "transcript": "Central, Trooper 412, I will be out at Interstate 80 Mile Marker 114 assisting stranded motorist.",
        "units": ["Trooper 412"],
        "evt_type": "Motorist Assist",
        "loc": "Interstate 80 Mile 114",
        "address": "I-80 MM 114",
        "status": "On Scene",
        "dur": 7.5,
    },
    {
        "transcript": "Medic 4 transporting to Parkland Hospital, priority two.",
        "units": ["Medic 4"],
        "evt_type": None,
        "loc": "Parkland Hospital",
        "address": None,
        "status": "Transporting",
        "dur": 5.1,
    },
    {
        "transcript": "All units Walton command, fire under control, checking for extension in attic.",
        "units": ["Battalion 1", "Engine 9"],
        "evt_type": "Structure Fire",
        "loc": "Walton Dr",
        "address": "1155 Walton Dr",
        "status": "On Scene",
        "dur": 6.5,
    },
    {
        "transcript": "Unit 112 Central, clear and 10-8 from the disturbance on Flat River Drive.",
        "units": ["Unit 112"],
        "evt_type": "Disturbance",
        "loc": "Flat River Drive",
        "address": None,
        "status": "In Service",
        "dur": 5.8,
    },
]


def seed_data(days: int = 2, entries_per_day: int = 75):
    """Seed synthetic transmissions and entity observations for target dates."""
    db = SessionLocal()
    try:
        today = date.today()
        created_logs = 0
        created_spans = 0
        created_entities = 0

        # Verify or resolve monitors
        monitors = db.query(Monitor).all()
        default_monitor_id = monitors[0].id if monitors else 1

        print(f"[*] Starting dummy data generation for {days} day(s) up to {today}...")

        for day_offset in range(days - 1, -1, -1):
            target_date = today - timedelta(days=day_offset)
            date_str = target_date.isoformat()

            # Generate spaced hours across the day (from 00:00 to 23:59 or current hour)
            max_hour = datetime.now().hour if day_offset == 0 else 23
            if max_hour == 0:
                max_hour = 12

            print(f"[+] Seeding {entries_per_day} entries for {date_str} (hours 0..{max_hour})...")

            for i in range(entries_per_day):
                tmpl = random.choice(DISPATCH_TEMPLATES)
                tg_name, mon_id = random.choice(SAMPLE_TALKGROUPS)

                # Random hour and minute
                h = random.randint(0, max_hour)
                m = random.randint(0, 59)
                s = random.randint(0, 59)
                ts = datetime.combine(target_date, time(h, m, s), tzinfo=timezone.utc)

                duration = round(tmpl["dur"] + random.uniform(-0.8, 1.2), 1)
                duration = max(3.0, duration)
                # Realistic RTF around 0.17x to 0.22x
                rtf = random.uniform(0.16, 0.21)
                proc_time = round(duration * rtf, 3)
                confidence = round(random.uniform(0.86, 0.96), 4)

                fn = f"{target_date.strftime('%Y%m%d')}_{h:02d}{m:02d}{s:02d}_{tg_name[:8]}.mp3"

                log_entry = LogEntry(
                    filename=fn,
                    timestamp=ts,
                    log_date=date_str,
                    duration=duration,
                    file_size=int(duration * 16000 * 2),
                    audio_path=f"audio_storage/{date_str}/{fn}",
                    transcript=tmpl["transcript"],
                    language="en",
                    confidence=confidence,
                    is_reviewed=False,
                    model_used="whisper-small.en-police-radio",
                    processing_time=proc_time,
                    talkgroup=tg_name,
                    created_at=ts,
                    is_deleted=False,
                )
                db.add(log_entry)
                db.flush()
                created_logs += 1

                # If this template has identifiable entities, register SpanStore & EntityObservation
                has_entities = bool(tmpl.get("units") or tmpl.get("evt_type") or tmpl.get("loc") or tmpl.get("status"))
                if has_entities:
                    span = SpanStore(
                        monitor_id=mon_id or default_monitor_id,
                        talkgroup=tg_name,
                        transcript=tmpl["transcript"],
                        evt_type=tmpl.get("evt_type"),
                        units=",".join(tmpl.get("units", [])) if tmpl.get("units") else None,
                        locations=tmpl.get("loc"),
                        addresses=tmpl.get("address"),
                        status=tmpl.get("status"),
                        time_mentions=None,
                        created_at=ts,
                        log_entry_id=log_entry.id,
                    )
                    db.add(span)
                    db.flush()
                    created_spans += 1

                    # Add normalized EntityObservations
                    # Units
                    for u in tmpl.get("units", []):
                        db.add(EntityObservation(
                            span_store_id=span.id,
                            monitor_id=mon_id or default_monitor_id,
                            talkgroup=tg_name,
                            log_entry_id=log_entry.id,
                            ts=ts,
                            label="UNIT",
                            canonical=u.strip().upper(),
                            raw=u.strip(),
                        ))
                        created_entities += 1

                    # Event Types
                    if tmpl.get("evt_type"):
                        db.add(EntityObservation(
                            span_store_id=span.id,
                            monitor_id=mon_id or default_monitor_id,
                            talkgroup=tg_name,
                            log_entry_id=log_entry.id,
                            ts=ts,
                            label="EVT_TYPE",
                            canonical=tmpl["evt_type"].strip().title(),
                            raw=tmpl["evt_type"].strip(),
                        ))
                        created_entities += 1

                    # Locations
                    if tmpl.get("loc"):
                        db.add(EntityObservation(
                            span_store_id=span.id,
                            monitor_id=mon_id or default_monitor_id,
                            talkgroup=tg_name,
                            log_entry_id=log_entry.id,
                            ts=ts,
                            label="LOC",
                            canonical=tmpl["loc"].strip().title(),
                            raw=tmpl["loc"].strip(),
                        ))
                        created_entities += 1

                    # Addresses
                    if tmpl.get("address"):
                        db.add(EntityObservation(
                            span_store_id=span.id,
                            monitor_id=mon_id or default_monitor_id,
                            talkgroup=tg_name,
                            log_entry_id=log_entry.id,
                            ts=ts,
                            label="ADDRESS",
                            canonical=tmpl["address"].strip().title(),
                            raw=tmpl["address"].strip(),
                        ))
                        created_entities += 1

                    # Status
                    if tmpl.get("status"):
                        db.add(EntityObservation(
                            span_store_id=span.id,
                            monitor_id=mon_id or default_monitor_id,
                            talkgroup=tg_name,
                            log_entry_id=log_entry.id,
                            ts=ts,
                            label="STATUS",
                            canonical=tmpl["status"].strip().title(),
                            raw=tmpl["status"].strip(),
                        ))
                        created_entities += 1

        db.commit()
        print(f"[+] Successfully committed dummy data:")
        print(f"    - LogEntry rows created: {created_logs}")
        print(f"    - SpanStore rows created: {created_spans}")
        print(f"    - EntityObservation rows created: {created_entities}")

    except Exception as exc:
        db.rollback()
        print(f"[!] Error seeding dummy data: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed dummy scanner radio data into ScanScribe DB.")
    parser.add_argument("--days", type=int, default=2, help="Number of days to populate up to today (default: 2)")
    parser.add_argument("--count", type=int, default=85, help="Number of transmissions per day (default: 85)")
    args = parser.parse_args()

    seed_data(days=args.days, entries_per_day=args.count)
