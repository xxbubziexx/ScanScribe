---
name: fastapi-production-patterns
description: >-
  Audits and enforces production-grade FastAPI practices: non-blocking asynchronous
  endpoints, Pydantic v2 schemas, database session lifecycle, WebSocket resilience,
  dependency injection, and robust exception handling.
---

# FastAPI Production Patterns Skill

This skill provides architectural guidelines and audit procedures for enterprise-grade FastAPI backends operating in continuous real-time environments (such as ScanScribe).

## When to Run This Skill
- The user requests an audit of FastAPI endpoints, routes, models, or backend services.
- Investigating event loop stalls, sluggish response times under load, or uncaught server errors.
- Designing new API routes, background workers, WebSocket handlers, or database operations.

---

## Prime Rules for FastAPI in Real-Time Systems

### 1. Zero Blocking on the Async Event Loop
- **Rule:** Never execute synchronous I/O, CPU-heavy tasks, or blocking network calls inside an `async def` route or async worker.
- **Forbidden in `async def`:**
  - `time.sleep()` -> Use `await asyncio.sleep()`
  - `requests.get()` / `urllib` -> Use `httpx.AsyncClient`
  - Synchronous disk file I/O (`open().read()`, `shutil.copy()`) -> Use `await asyncio.to_thread(...)` or `aiofiles`
  - Synchronous ML model inference (`engine.transcribe()`) -> Always wrap in `await asyncio.to_thread(...)`
  - Long blocking database queries -> Execute via thread pool or async SQLAlchemy session

### 2. Pydantic v2 Strict Typing & Validation
- **Explicit Schemas:** Every request body must be validated by a Pydantic v2 `BaseModel`.
- **Response Models:** Always define `response_model=...` on route decorators to ensure data contracts, prevent accidental schema leakage, and enable fast serialization.
- **Model Configuration:** Use Pydantic v2 idioms (`model_config = ConfigDict(from_attributes=True)` instead of v1 `Config.orm_mode = True`).

### 3. Database Session Lifecycle & WAL Mode Safety
- **Dependency Injection:** Inject database sessions using FastAPI's `Depends(get_db)` pattern with generator `yield`:
  ```python
  def get_db():
      db = SessionLocal()
      try:
          yield db
      finally:
          db.close()
  ```
- **Context Managers for Background Tasks:** In background workers or spawned tasks where `Depends` is not available, use explicit context managers:
  ```python
  with SessionLocal() as db:
      # queries
  ```
- **Concurrency & WAL:** With SQLite WAL mode, readers do not block writers and writers do not block readers, but only one write transaction can occur at a time. Keep write transactions short; avoid wrapping long external operations inside a single open database transaction.

### 4. WebSocket Lifecycle & Connection Pooling
- **Resilient Broadcast:** Never let one dead client disconnect crash the broadcast loop for other clients.
- **Exception Catching:** Always handle `WebSocketDisconnect` cleanly and remove dead sockets from connection pools.
- **Heartbeat & Keepalive:** Maintain ping/pong heartbeats to detect disconnected clients on mobile or unstable networks.

### 5. Lifespan Draining & Graceful Shutdown
- **Managed Background Tasks:** All background tasks should be registered with a central task manager (`task_manager.py`) so that application shutdown cleanly drains or cancels them without data loss.

---

## Step-by-Step Audit Procedure

### Step 1: Event Loop Non-Blocking Audit
1. Search all `async def` functions in `app/routes/` and `app/services/` for:
   - Blocking calls (`time.sleep`, `requests.`, `open(`, `shutil.`)
   - Synchronous database sessions without thread wrapping
2. Verify heavy inference or long I/O is wrapped with `asyncio.to_thread`.

### Step 2: Route & Schema Validation Audit
1. Verify all routes in `app/routes/` have typed parameters, Pydantic request models, and response models.
2. Verify status codes: `HTTPException` with appropriate 4xx/5xx codes instead of generic 500 crashes.

### Step 3: Database & WebSocket Connection Audit
1. Verify database sessions are closed in `finally` blocks or via generator dependencies.
2. Check `websocket_manager` for exception handling on `.send_json()` / `.send_text()`.

### Step 4: Verification Checks
1. Run backend pytest suite:
   ```bash
   pytest tests/
   ```
