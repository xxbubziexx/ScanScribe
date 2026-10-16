# ScanScribe Agentic Tool Calling & Reasoning Master Plan

## 1. Executive Summary & Vision

This plan defines the architectural and implementation roadmap for transitioning **ScanScribe Intelligence (`/intel`)** from a static context-injection pipeline to an **Agentic Tool-Calling & Structured Reasoning Engine**.

### Key Objectives:
1. **Agentic Tool Execution**: Empower the LLM with deterministic, read-only tools to search historical radio transmissions, zoom in on surrounding audio context around specific transmissions, inspect active incidents, and analyze talkgroup activity.
2. **ASR Uncertainty & Phonetic Intelligence Protocol**: The agent must explicitly recognize that Whisper/ASR audio transcriptions are fallible, subject to RF noise, clipped words, and phonetic misidentifications. The agent must reason with phonetic awareness, attempt alternative queries when keywords fail, state transcription ambiguities clearly without fabricating facts, and guide operators to verify via `[TX-...]` audio playback badges.
3. **"Show Tool Calls" UI Option**: An operator toggle allowing users to view or hide real-time tool execution steps, query parameters, and raw record hits.
4. **"Show Thinking" UI Option**: An operator toggle allowing users to inspect the model's intermediate chain-of-thought / reasoning process (supporting Gemini 2.0 thinking streams and OpenRouter reasoning tags).
5. **Channel Filter Streamlining**: Eliminate the manual talkgroup channel multi-select dropdown from the UI and backend requirements. The agent dynamically targets talkgroups via natural language intent and tool filtering.

---

## 2. Architectural Blueprint

### 2.1 Agent Tool Registry (Strictly Read-Only & Indexed)

To protect the live SQLite database (`data/scanscribe.db`) running live ingestion 24/7 on Ubuntu, all tools are strictly **read-only**, asynchronous, and execute against indexed columns with bounded record limits.

```
+---------------------------------------------------------------------------------+
|                                 ScanScribe LLM                                  |
+---------------------------------------------------------------------------------+
          |                                                               |
    [1. Tool Call]                                                [2. Final Response]
          v                                                               v
+-------------------------------------------------------------+   +---------------+
|                 FastAPI Agent Tool Registry                 |   | SSE Streamer  |
+-------------------------------------------------------------+   +---------------+
| • search_transcripts(query, tg, start_time, end_time, limit)|           |
| • get_surrounding_transmissions(tx_id, window_seconds)      |           | (Tokens &
| • get_incident_records(query, status, limit)                |           |  Citations)
| • get_talkgroup_activity(query, hours)                      |           |
+-------------------------------------------------------------+           v
          |                                                       +---------------+
          v                                                       | Frontend UI   |
+-------------------------------------------------------------+   | • Thinking    |
|               scanscribe.db (SQLite WAL Mode)               |   | • Tool Steps  |
+-------------------------------------------------------------+   | • Audio Badges|
                                                                  +---------------+
```

#### Tool Specifications:
1. **`search_transcripts`**:
   * *Arguments*: `query: str`, `talkgroup: Optional[str]`, `start_time: Optional[str]`, `end_time: Optional[str]`, `limit: int = 50`
   * *Description*: Search indexed radio audio transcripts by keyword, talkgroup, or timestamp range.
2. **`get_surrounding_transmissions`**:
   * *Arguments*: `tx_id: int`, `window_seconds: int = 180`
   * *Description*: Retrieve radio transmissions occurring immediately before and after a specific transmission ID to examine conversational dispatch context.
3. **`get_incident_records`**:
   * *Arguments*: `query: Optional[str]`, `status: Optional[str] = "active"`, `limit: int = 20`
   * *Description*: Query classified incidents, addresses, assigned units, and incident categories from the incident intelligence pipeline.
4. **`get_talkgroup_activity`**:
   * *Arguments*: `query: Optional[str]`, `hours: int = 24`
   * *Description*: Inspect talkgroup traffic statistics, active channels, and recent transmission volume without loading all raw transcripts.

---

### 2.2 ASR Fallibility & Phonetic Reasoning Protocol

A fundamental reality of public safety SDR ingest and local Whisper speech-to-text models is that **transcriptions are inherently imperfect**. Audio is frequently degraded by:
* RF multi-path fading, analog hum, DMR/P25 digital artifacts, and CTCSS/DCS squelch bursts.
* Heavy vehicle siren background noise, SCBA respirators, clipped microphone key-ups, and dispatcher brevity.
* Localized phonetic confusion (e.g., street names like "Duval" transcribed as "do all", unit callsigns like "Battalion 1" transcribed as "Italian one", 10-codes like "10-50" transcribed as "ten fifty" or "tent 50").

#### Agent Cognitive Guidelines (Mandatory System Prompt Rules):
1. **Never Assume 100% Lexical Veracity**:
   * The agent must treat raw transcripts as *noisy phonetic approximations*, not verbatim legal depositions.
   * If a transcript contains an anomalous or gibberish phrase in the middle of a tactical call (e.g., *"en route with cheese"* instead of *"en route with lights"*), the agent must recognize it as an ASR misidentification and interpret the likely intent from context or flag the ambiguity.
2. **Multi-Query Phonetic Tool Search**:
   * When using `search_transcripts`, if a primary keyword yields no results or partial results, the agent must systematically attempt phonetic alternates, numeric variations (e.g. searching both `"10-50"` and `"ten fifty"` or `"rollover"`), and broader talkgroup/time searches.
3. **Contextual Triangulation (`get_surrounding_transmissions`)**:
   * When an ambiguous or suspect transmission is identified, the agent must invoke `get_surrounding_transmissions` to examine the full dispatch cadence (dispatcher acknowledgment, secondary unit responses, status updates) to corroborate the actual event.
4. **Transparent Uncertainty & Operator Verification**:
   * When reporting an incident based on noisy transcripts, the agent must state:
     > *"Transcript indicates possible [suspect phrase], but audio quality appears degraded. Verify via [TX-12345]."*
   * The agent must consistently prompt operators to verify critical details by clicking the `[TX-...]` badge to listen to the raw audio recording.

---

### 2.3 Streaming Protocol Expansion (Server-Sent Events)

The SSE streaming endpoint (`POST /api/chat/threads/{thread_id}/stream`) expands its event envelope to stream thinking and tool calling steps in real-time without blocking the user:

| Event Type | Payload Format | Description |
| :--- | :--- | :--- |
| `event: meta` | `{"type": "meta", "model": "...", "time_desc": "..."}` | Initial query initialization metadata. |
| `event: thinking` | `{"type": "thinking", "content": "Analyzing dispatch timestamps..."}` | Incremental reasoning/thought tokens. |
| `event: tool_call` | `{"type": "tool_call", "call_id": "call_1", "tool": "search_transcripts", "arguments": {...}}` | Emitted when the agent initiates a tool call. |
| `event: tool_result` | `{"type": "tool_result", "call_id": "call_1", "tool": "search_transcripts", "summary": "Found 8 records", "count": 8}` | Emitted when tool execution completes with summary data. |
| `event: token` | `{"type": "token", "content": "..."}` | Final answer markdown tokens with citations `[TX-...]`. |
| `event: done` | `{"type": "done", "cited_log_ids": [...]}` | Stream completion signal. |
| `event: error` | `{"type": "error", "error": "..."}` | Graceful error notification. |

---

### 2.4 UI & Operator Experience (`/intel`)

#### 1. Removal of Talkgroup Channel Filter
* **TimeScopeBar**:
  * Strip the talkgroup dropdown button, popup checklist, and clear button.
  * TimeScopeBar now focuses exclusively on temporal scope (`Past 1h`, `Past 4h`, `Past 12h`, `Today`, `Yesterday`, `Custom`) and view toggles.
* **Backend**:
  * Remove `talkgroups` parameter requirement from `ChatPromptInput` and `ChatThreadCreate` (remain optional for backwards compatibility).

#### 2. "Show Tool Calls" and "Show Thinking" Toggles
* **Placement**: Located on the right side of `TimeScopeBar` (or chat header).
* **Controls**:
  * `[⚡ Show Tools]` (Toggle switch / badge with active state indicator).
  * `[🧠 Show Thinking]` (Toggle switch / badge with active state indicator).
  * Values persisted in `localStorage` (`scanscribe_intel_show_tools`, `scanscribe_intel_show_thinking`).
* **Message Presentation (`ChatMessageList`)**:
  * **Thinking Card**: Collapsible container at the top of the assistant response.
    * Active state: Pulsing amber/cyan indicator `Analyzing radio logs & timeline...`
    * Completed state: Accordion `Thought Process (X lines)` - collapsed by default if toggle is off, open or accessible if toggle is on.
  * **Tool Execution Card**: Collapsible audit trail showing:
    * Tool name with icon (e.g. `search_transcripts`).
    * Input arguments (e.g. `query: "code 3", time: "18:00 - 19:00"`).
    * Results indicator (e.g. `Returned 6 transmissions`).

---

## 3. Database Schema Updates (Alembic Migration)

To persist thought traces and tool executions across page reloads and thread history without bloating the text content:

### Alembic Migration: `xxxx_add_thought_and_tools_to_chat_messages.py`
```python
def upgrade():
    op.add_column('chat_messages', sa.Column('thought', sa.Text(), nullable=True))
    op.add_column('chat_messages', sa.Column('tool_calls', sa.Text(), nullable=True)) # JSON array of tool execution records
```

---

## 4. Multi-Phase Implementation Steps

### Phase 1: Database Migration & Schema Alignment
- [ ] Create Alembic migration adding `thought` and `tool_calls` nullable columns to `chat_messages`.
- [ ] Update SQLAlchemy model in [`app/models/chat.py`](file:///a:/Scanscribe_Projects/scanscribe/app/models/chat.py).
- [ ] Update Pydantic v2 schemas in [`app/schemas/chat.py`](file:///a:/Scanscribe_Projects/scanscribe/app/schemas/chat.py):
  - Add `thought: Optional[str]` and `tool_calls: Optional[List[Dict[str, Any]]]` to `ChatMessageOut`.
  - Remove mandatory `talkgroups` in `ChatPromptInput` and `ChatThreadCreate`.
- [ ] Run migration test: `alembic upgrade head`.

### Phase 2: Agent Tools Service Engine & ASR Protocol Prompts
- [ ] Update system prompt builder in [`app/services/chat_context.py`](file:///a:/Scanscribe_Projects/scanscribe/app/services/chat_context.py) with the **ASR Fallibility & Phonetic Reasoning Protocol**:
  - Treat raw Whisper transcripts as noisy phonetic approximations.
  - Require contextual disambiguation of garbled words, 10-codes, and street names.
  - Advise operator verification via `[TX-...]` audio playback badges whenever transcription uncertainty exists.
- [ ] Create [`app/services/agent_tools.py`](file:///a:/Scanscribe_Projects/scanscribe/app/services/agent_tools.py):
  - Define tool schemas (OpenAI / Gemini function calling format).
  - Implement async executor functions:
    * `execute_search_transcripts(db, query, talkgroup, start_time, end_time, limit)`
    * `execute_get_surrounding_transmissions(db, tx_id, window_seconds)`
    * `execute_get_incident_records(db, query, status, limit)`
    * `execute_get_talkgroup_activity(db, query, hours)`
- [ ] Unit tests for tool executors in [`tests/test_agent_tools.py`](file:///a:/Scanscribe_Projects/scanscribe/tests/test_agent_tools.py).

### Phase 3: Streaming Engine with Tool Calling & Reasoning
- [ ] Update [`app/services/chat_streamer.py`](file:///a:/Scanscribe_Projects/scanscribe/app/services/chat_streamer.py):
  - Support Gemini Function Calling loop (`tools` declaration, handling `tool_call` response, dispatching execution, feeding `tool_response` back to Gemini).
  - Support OpenRouter / OpenAI Function Calling loop (`tools`, `tool_calls`, role `tool`).
  - Stream `event: thinking` for models providing native thought tokens (e.g. Gemini 2.0 Flash Thinking) or extract `<thought>` blocks from reasoning models (e.g. DeepSeek-R1 / Qwen).
  - Stream `event: tool_call` and `event: tool_result` as they occur.
- [ ] Update [`app/routes/chat.py`](file:///a:/Scanscribe_Projects/scanscribe/app/routes/chat.py):
  - Persist `thought` and `tool_calls` into `ChatMessage` when stream completes.

### Phase 4: Frontend UI Modernization
- [ ] Update [`TimeScopeBar.tsx`](file:///a:/Scanscribe_Projects/scanscribe/app/frontend/src/pages/Intel/components/TimeScopeBar.tsx):
  - Remove Talkgroup filter dropdown and state.
  - Add operator toggle switches:
    * `Show Tools` (icon + label, toggle styling)
    * `Show Thinking` (icon + label, toggle styling)
- [ ] Update [`ChatMessageList.tsx`](file:///a:/Scanscribe_Projects/scanscribe/app/frontend/src/pages/Intel/components/ChatMessageList.tsx):
  - Build collapsible `ThinkingAccordion` component.
  - Build collapsible `ToolCallCard` component showing arguments and execution status.
  - Respect `showTools` and `showThinking` toggles.
- [ ] Update [`IntelPage.tsx`](file:///a:/Scanscribe_Projects/scanscribe/app/frontend/src/pages/Intel/IntelPage.tsx):
  - Remove `selectedTalkgroups` state and `listTalkgroups` query dependencies.
  - Wire up persistent preferences for `showTools` and `showThinking`.
  - Handle new SSE event types (`thinking`, `tool_call`, `tool_result`).

### Phase 5: Verification & Safety Audits
- [ ] Validate zero-regression performance on SQLite WAL concurrency under simulated audio ingest.
- [ ] Pytest suite validation (`pytest tests/`).
- [ ] Frontend type check and production bundle compilation (`npm run build`).
- [ ] Update documentation in `ACTIVE_CONTEXT.md` and user manual.
