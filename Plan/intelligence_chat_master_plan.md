# ScanScribe Scanner Intelligence Master Plan (Intel)

## 1. Executive Summary & Vision

**ScanScribe Intelligence** (`/intel`) provides an interactive natural-language query interface designed for serious radio hobbyists, SDR systems operators, and the RadioReference / r/policescanner communities.

Rather than manually searching through hundreds of recorded audio files or filtering large volumes of raw database rows, users can submit conversational queries against captured radio traffic:
* "What occurred at the Walmart location today at 18:00?"
* "Summarize scanner activity on County Fire TAC 1 over the last four hours."
* "Why was unit 112 responding code 3 down the highway?"
* "Where was Engine 4 dispatched this morning around 08:30?"
* "List all pursuit or traffic stop transmissions on Highway 61 today."

The system integrates time-window database retrieval over local `LogEntry` records, long-context LLM prompt assembly, non-blocking asynchronous streaming (Server-Sent Events), and interactive audio citation badges allowing immediate playback and verification of original transmissions.

> **Product Scope & Standards**:
> ScanScribe is engineered to professional grade for serious radio enthusiasts, SDR monitoring stations, and community scanner archivists. It is not a certified 911 dispatch console or public safety CAD suite. All terminology, UI layout, and system behavior reflect a clean, instrument-grade technical application.

---

## 2. Architectural Decisions

### 2.1 Navigation & Route Placement
* **Route:** `/intel`
* **Label:** `Intelligence` (Nav label: `Intel`)
* **Placement in TopNav:**
  Located between `Insights` and `Events`:
  ```tsx
  { to: '/', label: 'Command Center', icon: '🗺️', end: true },
  { to: '/dashboard', label: 'Audio Feed', icon: '📻' },
  { to: '/insights', label: 'Insights', icon: '📊' },
  { to: '/intel', label: 'Intel', icon: '💬' },
  { to: '/events', label: 'Events', icon: '🚨' },
  ```
* **Accessibility:** Available to authenticated users across desktop monitoring setups, laptops, and mobile browser viewports (`100dvh`).

### 2.2 Database Architecture: Unified SQLite WAL Database
* **Decision: Store chat tables within `data/scanscribe.db` via Alembic migrations.**
  * *Rationale:* Prior refactoring consolidated disparate SQLite databases into a single WAL-mode SQLite database (`data/scanscribe.db`). Maintaining an isolated database file for chat history introduces redundant connection pools, OS-level file locking issues on Windows, and split backup procedures.
  * Storing `chat_threads` and `chat_messages` in `data/scanscribe.db` preserves referential integrity (`FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE`), integrates with existing retention and backup workflows, and adheres strictly to **AGENTS.md Section 2 (Alembic Migrations Only)**.

### 2.3 Time-Window Retrieval & Token Optimization
* **Preset Controls:**
  * Quick selections: `Past 1 Hour`, `Past 4 Hours`, `Past 12 Hours`, `Today` (00:00 to current time), `Yesterday`, and `Custom Range`.
* **Talkgroup Filtering:**
  * Multi-select talkgroup filter to isolate specific channels (e.g., `Police Dispatch`, `Fire Ground 1`) and reduce prompt token overhead.
* **Volume Constraints:**
  * Indexed database queries on `(timestamp, is_deleted, talkgroup)`.
  * Configurable transmission threshold (default limit: 2,500 transmissions per query window). When thresholds are exceeded, the UI presents transmission counts and prompts the user to refine the time window or filter by talkgroup.

### 2.4 Grounding & Audio Playback Citations
* **Context Formatting:**
  Each transmission injected into the LLM context includes a structured identifier, timestamp, and talkgroup metadata:
  ```text
  [TX-10482 | 2026-10-14 18:04:12 | TG: POLICE_DISP]: "Dispatch, 112 en route code 3 to Highway 61 and Main for a 10-50 rollover."
  ```
* **Citation Parsing & Audio Playback:**
  * System instructions require the model to cite transmission tags for factual statements (`...Unit 112 responded code 3 to a two-vehicle collision [TX-10482]`).
  * The frontend markdown parser converts `[TX-10482]` references into interactive badges:
    * Displays timestamp and talkgroup on hover.
    * Clicking triggers inline audio playback of the original `.mp3`/`.wav` recording or opens the audio preview modal.

### 2.5 Asynchronous Streaming LLM Service
* Adheres to **AGENTS.md Rules 1 & 2**: Non-blocking asynchronous I/O (`httpx.AsyncClient`) using Server-Sent Events (`text/event-stream`). No synchronous calls in the request path to ensure background audio ingestion is never impacted.
* Dedicated `chat` configuration section in `config.yml` supporting OpenRouter and Google Gemini models.

---

## 3. Data Schema & Models

### 3.1 Alembic Migration
```python
# alembic/versions/xxxx_create_chat_tables.py
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_table(
        'chat_threads',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('title', sa.String(255), nullable=False, default='New Intel Query'),
        sa.Column('time_scope_type', sa.String(50), default='today'), # '1h', '4h', '12h', 'today', 'custom'
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('talkgroups', sa.Text(), nullable=True), # JSON array of selected talkgroups
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)')),
    )
    
    op.create_table(
        'chat_messages',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('thread_id', sa.Integer(), sa.ForeignKey('chat_threads.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('role', sa.String(20), nullable=False), # 'user', 'assistant', 'system'
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('cited_log_ids', sa.Text(), nullable=True), # JSON array of LogEntry IDs cited in the response
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)')),
    )
```

---

## 4. API Specification

### 4.1 Thread Management
* `GET /api/chat/threads` — Retrieve thread history for the authenticated user.
* `POST /api/chat/threads` — Create a new thread with default time scope parameters.
* `GET /api/chat/threads/{thread_id}` — Fetch thread details and message log.
* `DELETE /api/chat/threads/{thread_id}` — Remove thread and associated messages.

### 4.2 Streaming Query Execution
* `POST /api/chat/threads/{thread_id}/stream`
  * **Payload:**
    ```json
    {
      "prompt": "What happened at Walmart today at 6pm?",
      "time_scope": {
        "preset": "today",
        "start_time": null,
        "end_time": null
      },
      "talkgroups": ["POLICE_DISP", "FIRE_DISP"]
    }
    ```
  * **Response:** `text/event-stream` returning:
    * `event: meta` — Context metrics (transmissions processed, token count, query duration).
    * `event: token` — Incremental response text chunks.
    * `event: done` — Completion signal with cited transmission identifiers.
    * `event: error` — Error handling without abrupt connection drops.

### 4.3 Transmission Audio Verification
* `GET /api/chat/transmissions/{log_id}` — Fetch transcript details, audio file path, talkgroup, and related incident metadata.

---

## 5. Multi-Phase Implementation Roadmap

### Phase 1: Database Migration & Configuration
- [ ] Create Alembic revision for `chat_threads` and `chat_messages` in `alembic/versions/`.
- [ ] Define SQLAlchemy models in [`app/models/chat.py`](file:///a:/Scanscribe_Projects/scanscribe/app/models/chat.py) and export via [`app/models/__init__.py`](file:///a:/Scanscribe_Projects/scanscribe/app/models/__init__.py).
- [ ] Implement Pydantic v2 schemas in [`app/schemas/chat.py`](file:///a:/Scanscribe_Projects/scanscribe/app/schemas/chat.py).
- [ ] Add `chat` configuration parameters to [`app/config.py`](file:///a:/Scanscribe_Projects/scanscribe/app/config.py) and [`config.yml.example`](file:///a:/Scanscribe_Projects/scanscribe/config.yml.example).

### Phase 2: Asynchronous LLM Engine & Context Pipeline
- [ ] Implement `ChatContextBuilder` in [`app/services/chat_context.py`](file:///a:/Scanscribe_Projects/scanscribe/app/services/chat_context.py):
  - Efficient indexed queries against `LogEntry`.
  - Format transmissions into structured `[TX-<id> | <time> | <tg>]` entries.
  - Radio terminology system prompt (handling 10-codes, callsigns, radio brevity, and SDR noise).
- [ ] Implement `AsyncChatStreamer` in [`app/services/chat_streamer.py`](file:///a:/Scanscribe_Projects/scanscribe/app/services/chat_streamer.py) using `httpx.AsyncClient` supporting OpenRouter and Gemini streaming endpoints.
- [ ] Create FastAPI endpoints in [`app/routers/chat.py`](file:///a:/Scanscribe_Projects/scanscribe/app/routers/chat.py) with SSE support.

### Phase 3: Frontend User Interface (`/intel`)
- [ ] Register `/intel` route in [`App.tsx`](file:///a:/Scanscribe_Projects/scanscribe/app/frontend/src/App.tsx) and navigation item in [`TopNav.tsx`](file:///a:/Scanscribe_Projects/scanscribe/app/frontend/src/components/layout/TopNav.tsx).
- [ ] Build UI modules in `app/frontend/src/pages/Intel/`:
  - `IntelPage.tsx`: Main layout with thread history sidebar and conversation view.
  - `TimeScopeBar.tsx`: Time presets (1h, 4h, 12h, Today, Custom) and talkgroup selectors.
  - `ChatMessageList.tsx` & `ChatMessageItem.tsx`: Clean message presentation with autoscroll.
  - `ChatInputBox.tsx`: Input area with keyboard shortcuts and sample query prompts.
- [ ] Implement citation parser rendering `[TX-...]` as interactive badges.

### Phase 4: Audio Playback Integration & Verification
- [ ] Configure `[TX-...]` citation badges to trigger audio playback of the original transmission.
- [ ] Provide quick navigation links to the transmission in the Audio Feed (`/dashboard?tx=...`) or associated event in `/events`.
- [ ] Implement default sample prompts for common scanner queries:
  - "Summarize scanner activity from the past hour"
  - "List all fire and rescue dispatches today"
  - "Search for traffic stops and collisions on Highway 61"
  - "Explain why unit 112 was responding code 3"

### Phase 5: Verification, Benchmarking & Documentation
- [ ] Add pytest unit tests covering time-window queries, context formatting, and chat endpoints.
- [ ] Validate frontend build integrity (`npm run build`).
- [ ] Verify zero latency impact on background audio ingestion pipelines.
- [ ] Update [`ACTIVE_CONTEXT.md`](file:///a:/Scanscribe_Projects/scanscribe/ACTIVE_CONTEXT.md) and record model handoff.
