# Phase 2: Database Consolidation & Schema Migrations

> **Phase Order**: 2 of 5  
> **Status**: Ready for Implementation  
> **Estimated Execution Time**: ~2–3 hours  
> **Target Files**: `app/database.py`, `app/models/`, `alembic/`, `scripts/migrate_databases.py`

---

## 1. Objectives

1. Merge the three fragmented SQLite databases (`scanscribe.db`, `scanscribe_logs.db`, `scanscribe_events.db`) into a single, high-performance database (`data/scanscribe.db`).
2. Configure SQLite concurrency primitives (WAL mode, 5000ms busy timeout, foreign key enforcement) to eradicate "database is locked" exceptions.
3. Replace runtime PRAGMA checks and destructive table-drop routines in [`app/database.py`](file:///a:/Scanscribe_Projects/scanscribe/app/database.py) with standard **Alembic** versioned migrations.
4. Provide a non-destructive data migration script that seamlessly consolidates existing user databases.
5. Normalize polymorphic data columns (e.g. `Event.units` and timezone representations).

---

## 2. Current vs. Target Database Architecture

### Current Architecture (Fragmented):
```
┌─────────────────────────┐  ┌─────────────────────────┐  ┌─────────────────────────┐
│      scanscribe.db      │  │   scanscribe_logs.db    │  │   scanscribe_events.db  │
├─────────────────────────┤  ├─────────────────────────┤  ├─────────────────────────┤
│ • users                 │  │ • log_entries           │  │ • monitors              │
│                         │  │ • hour_summaries        │  │ • events                │
│                         │  │                         │  │ • event_transcript_links│
│                         │  │                         │  │ • span_store            │
│                         │  │                         │  │ • entity_observations   │
│                         │  │                         │  │ • pipeline_debug_log    │
│                         │  │                         │  │ • system_settings       │
└─────────────────────────┘  └─────────────────────────┘  └─────────────────────────┘
         ▲                                ▲                            ▲
         │ (Separate Engine)              │ (Separate Engine)          │ (Separate Engine)
         └───────────────────────┬────────┴────────────────────────────┘
                                 │
                   NO FOREIGN KEYS POSSIBLE ACROSS DBs!
             (event_transcript_links.log_entry_id is an orphan int)
```

### Target Architecture (Unified with True Constraints):
```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       data/scanscribe.db (WAL Mode)                         │
├─────────────────────────────────────────────────────────────────────────────┤
│  users ◄────────────── (Audit tracking)                                     │
│  monitors ──────────┐                                                       │
│                     │ 1:N (FK)                                              │
│                     ▼                                                       │
│  events ◄─────┐    span_store ◄────┐                                        │
│               │ 1:N                │ 1:N                                    │
│               │ (FK)               │ (FK)                                   │
│  event_transcript_links ─────► log_entries (FK)                             │
│       │                            │ 1:N (FK)                               │
│       │                            ▼                                        │
│       └──────────────────────► entity_observations                          │
│                                                                             │
│  system_settings  •  pipeline_debug_log  •  hour_summaries                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Database Engine & Concurrency Primitives

In [`app/database.py`](file:///a:/Scanscribe_Projects/scanscribe/app/database.py), replace the three separate engines with a single, hardened SQLAlchemy engine configured with SQLite best practices:

```python
"""Unified database configuration with WAL mode and connection pooling."""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from .config import get_settings

settings = get_settings()

DATABASE_URL = f"sqlite:///{settings.db_path}"

engine = create_engine(
    DATABASE_URL,
    connect_args={
        "check_same_thread": False,
        "timeout": 15,  # 15s driver level lock wait
    },
    pool_pre_ping=True,
    echo=False,
)

# Enforce SQLite PRAGMAs on every connection checkout
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    # Write-Ahead Logging allows concurrent readers alongside writers
    cursor.execute("PRAGMA journal_mode=WAL;")
    # Wait up to 5000ms if another thread is writing instead of throwing immediately
    cursor.execute("PRAGMA busy_timeout=5000;")
    # Enforce referential integrity
    cursor.execute("PRAGMA foreign_keys=ON;")
    # Synchronous NORMAL is fully crash-safe in WAL mode and drastically faster
    cursor.execute("PRAGMA synchronous=NORMAL;")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """FastAPI dependency yielding database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

> [!IMPORTANT]
> Backward-compatibility aliases (`get_logs_db`, `get_events_db`) will simply yield `get_db()` during the transitional phase to prevent breaking untouched routers.

---

## 4. Normalizing Schema & Constraints

Update [`app/models/event.py`](file:///a:/Scanscribe_Projects/scanscribe/app/models/event.py) to bind models to the unified `Base` and establish valid foreign keys:

### 1. `EventTranscriptLink` with Cascade Deletes:
```python
class EventTranscriptLink(Base):
    __tablename__ = "event_transcript_links"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    log_entry_id = Column(Integer, ForeignKey("log_entries.id", ondelete="CASCADE"), nullable=False, index=True)
    entities_json = Column(Text, nullable=True)
    llm_reason = Column(Text, nullable=True)
    linked_at = Column(DateTime(timezone=True), default=utcnow)
    
    # Relationships
    event = relationship("Event", back_populates="transcript_links")
    log_entry = relationship("LogEntry")
```

### 2. Strict Type Standardization for `Event.units`:
Eliminate the `# JSON array or comma-separated` ambiguity:
```python
# app/models/event.py
# Store strictly as a JSON string representing List[str]
units = Column(Text, nullable=True, default="[]")

@property
def units_list(self) -> List[str]:
    """Guaranteed List[str] accessor."""
    if not self.units:
        return []
    try:
        val = json.loads(self.units)
        return val if isinstance(val, list) else [str(val)]
    except Exception:
        return [u.strip() for u in self.units.split(",") if u.strip()]
```

---

## 5. Alembic Setup & Migration Workflow

### 1. Initialize Alembic:
From project root:
```bash
alembic init alembic
```

### 2. Configure `alembic/env.py`:
Point `target_metadata` to the unified model registry:
```python
from app.database import Base
from app.models import user, log_entry, event, hour_summary
from app.config import get_settings

config.set_main_option("sqlalchemy.url", f"sqlite:///{get_settings().db_path}")
target_metadata = Base.metadata
```

### 3. Replace Dangerous `init_db()` in [`app/database.py`](file:///a:/Scanscribe_Projects/scanscribe/app/database.py):
Delete all runtime `PRAGMA table_info` checks and `DROP TABLE IF EXISTS span_store`. Replace with:
```python
def init_db():
    """Ensure database schema is up to date via Alembic."""
    from alembic import command
    from alembic.config import Config
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
```

---

## 6. Zero-Loss Legacy Data Migration Script

Create [`scripts/migrate_databases.py`](file:///a:/Scanscribe_Projects/scanscribe/scripts/migrate_databases.py) to consolidate existing user data:

```python
"""Migrate legacy three-database setup into unified scanscribe.db."""
import sqlite3
import shutil
from pathlib import Path

def migrate_to_unified(data_dir: Path):
    target_db = data_dir / "scanscribe.db"
    logs_db = data_dir.parent / "logs" / "scanscribe_logs.db"
    events_db = data_dir / "scanscribe_events.db"

    # Backup existing databases
    for p in [target_db, logs_db, events_db]:
        if p.is_file():
            shutil.copy2(p, p.with_suffix(".db.bak"))
            print(f"Backed up {p.name}")

    conn = sqlite3.connect(target_db)
    cur = conn.cursor()

    if logs_db.is_file():
        cur.execute(f"ATTACH DATABASE '{logs_db}' AS legacy_logs;")
        cur.execute("INSERT OR IGNORE INTO log_entries SELECT * FROM legacy_logs.log_entries;")
        cur.execute("INSERT OR IGNORE INTO hour_summaries SELECT * FROM legacy_logs.hour_summaries;")
        conn.commit()
        cur.execute("DETACH DATABASE legacy_logs;")
        print("Migrated logs data successfully.")

    if events_db.is_file():
        cur.execute(f"ATTACH DATABASE '{events_db}' AS legacy_events;")
        cur.execute("INSERT OR IGNORE INTO monitors SELECT * FROM legacy_events.monitors;")
        cur.execute("INSERT OR IGNORE INTO events SELECT * FROM legacy_events.events;")
        cur.execute("INSERT OR IGNORE INTO event_transcript_links SELECT * FROM legacy_events.event_transcript_links;")
        cur.execute("INSERT OR IGNORE INTO span_store SELECT * FROM legacy_events.span_store;")
        cur.execute("INSERT OR IGNORE INTO entity_observations SELECT * FROM legacy_events.entity_observations;")
        cur.execute("INSERT OR IGNORE INTO pipeline_debug_log SELECT * FROM legacy_events.pipeline_debug_log;")
        cur.execute("INSERT OR IGNORE INTO system_settings SELECT * FROM legacy_events.system_settings;")
        conn.commit()
        cur.execute("DETACH DATABASE legacy_events;")
        print("Migrated events data successfully.")

    conn.close()
```

---

## 7. Verification Criteria

- [ ] All three databases successfully merge into `data/scanscribe.db` with identical row counts verified by count queries.
- [ ] SQLite connection reports `journal_mode=wal` and `foreign_keys=1`.
- [ ] Deleting a `LogEntry` properly cascades or nullifies references without orphaned integer IDs.
- [ ] `alembic upgrade head` runs idempotently with zero errors.
- [ ] No `PRAGMA table_info` or `DROP TABLE` queries exist in [`app/database.py`](file:///a:/Scanscribe_Projects/scanscribe/app/database.py).
