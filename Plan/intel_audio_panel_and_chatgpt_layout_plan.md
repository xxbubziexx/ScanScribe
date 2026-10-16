# ScanScribe: Intel Audio Control Panel & ChatGPT Layout Refactor Plan

## Executive Overview
This plan modernizes the `/intel` Scanner Intelligence page with two major architectural and UX upgrades requested by the user:
1. **Fixing Citation Links & Introducing a Dedicated Right-Side Audio Control Panel**:
   - Resolve broken `[TX #...]` hyperlinks (e.g. `[TX #492983](http://localhost:8000/app/intel)`) by standardizing markdown link interception and system prompt guidelines.
   - Replace the intrusive full-screen modal with a sleek, docked/slide-out **Right-Side Audio Control Panel**.
   - Auto-aggregate and display all cited radio transmissions for the conversation or active response.
   - Equip the panel with an instrument-grade **custom audio playback bar** (scrubber, waveform visualization, playback speeds, continuous chronological auto-play, skip ±5s, and volume control).
2. **ChatGPT-Style Layout Migration**:
   - Retire the mobile/SMS rounded-bubble layout (`items-end` blue bubbles vs `items-start` gray boxes).
   - Adopt a modern, centered document layout (`max-w-3xl` / `max-w-4xl`) with distinct Operator vs Intel row treatments, inline collapsable thinking accordions, structured tool execution traces, action bars (copy text, jump to audio), and a modern floating prompt box.

---

## Architecture & Component Breakdown

```
+-------------------------------------------------------------------------------------------------------------------+
|  Top Scope Bar (Time preset, Show Tools toggle, Show Thinking toggle, Audio Panel toggle [x cited clips])         |
+------------------------------------------------------------------------------------+------------------------------+
|                                                                                    |                              |
|  ChatGPT-Style Conversation Stream (Centered max-w-3xl / max-w-4xl)                 |  Right-Side Audio Panel      |
|                                                                                    |  (Docked desktop / drawer)   |
|  [Operator Avatar] User prompt (clean, crisp, no bubble pill)                      |                              |
|                                                                                    |  +------------------------+  |
|  [ScanScribe Intel] Assistant Response:                                            |  | Active Player Station  |  |
|    - [Thinking Accordion] (collapsable, reasoning effort)                          |  | [Waveform / Scrubber]  |  |
|    - [Tool Call Cards] (agent execution traces)                                    |  | [Play/Pause] [Skip ±5] |  |
|    - Clean Markdown Document (headings, bullet points, citations)                  |  | [Speed: 1x/1.25x/1.5x] |  |
|      - [TX #492983 🔊] clickable chip -> focuses clip in right panel               |  | [Continuous Auto-play] |  |
|    - Action Footer: [Copy Response] [Open Cited Audio (3)]                         |  +------------------------+  |
|                                                                                    |                              |
|                                                                                    |  Cited Transmission Queue    |
|  --------------------------------------------------------------------------------  |  - TX #492983 (Dispatch)     |
|                                                                                    |    10:14:02 PM | 4.2s        |
|  [Floating Prompt Box with Auto-expanding Textarea & Stop/Send Controls]           |  - TX #492985 (Tac 1)        |
|                                                                                    |    10:14:15 PM | 6.8s        |
+------------------------------------------------------------------------------------+------------------------------+
```

---

## Detailed Implementation Phases

### Phase 1: Citation Link Interception & Prompt Hardening
- **Root Cause Analysis**:
  - LLMs sometimes wrap citations in standard markdown anchor syntax: `[TX #492983](http://localhost:8000/app/intel)` or `[TX #492983](...)`.
  - In `ChatMessageList.tsx`, `preprocessMarkdownCitations` regex only looked for `\[TX[-#\s]*(\d+)\]` when not followed by `(...)`. When a markdown link was present, ReactMarkdown received `<a href="http://...">` and rendered a standard anchor that reloaded `/app/intel`.
- **Backend Prompt Hardening** ([`app/services/chat_context.py`](file:///a:/Scanscribe_Projects/scanscribe/app/services/chat_context.py)):
  - Explicitly update `AGENT_TOOL_RULES` and system prompt with negative constraints:
    `"CITATION SYNTAX: When citing a transmission, ALWAYS output the exact token [TX-<id>] (e.g. [TX-492983]). NEVER generate markdown URL hyperlinks (e.g. do NOT write [TX-492983](http://...) or [TX-492983](/app/intel)). Simply write [TX-<id>]."`
- **Frontend Regex Robustness** ([`app/frontend/src/pages/Intel/components/ChatMessageList.tsx`](file:///a:/Scanscribe_Projects/scanscribe/app/frontend/src/pages/Intel/components/ChatMessageList.tsx)):
  - Update `preprocessMarkdownCitations` to match:
    1. Any existing markdown link whose text is a transmission ID: `\[TX[-#\s]*(\d+)\]\([^)]+\)` -> `[TX #$1](tx:$1)`
    2. Bracketed IDs: `\[TX[-#\s]*([0-9,\sTX#\-]+)\]` -> mapped to `[TX #$n](tx:$n)`
    3. Bare citations: `TX[-#\s]+(\d+)` -> `[TX #$1](tx:$1)`
  - In ReactMarkdown `components.a`:
    - Intercept any `href` starting with `tx:` OR any link whose children/text matches `TX[-#\s]*\d+`.
    - Prevent default navigation and dispatch `onSelectTx(txId)` / activate the right-side audio controller.


### Phase 2: Agent NER Lookup Tool (`lookup_ner_entities`)
- **Primary Use Cases**:
  - **Unit Activity Timelines** (e.g. *"What did unit 112 do today?"*, *"Where has Medic 4 responded?"*):
    - Agent invokes `lookup_ner_entities(query="112", label="UNIT")`.
    - Returns a chronological event timeline tracking unit callouts, dispatches, status changes (en route, on scene, clear), and mutual aid assignments across talkgroups.
  - **Location & Address History** (e.g. *"What happened at 1155 walton dr?"*, *"Any activity near Walmart?"*):
    - Agent invokes `lookup_ner_entities(query="walton", label="ADDRESS")` (or `LOC`).
    - Returns all radio transmissions referencing the address, including incident call types (`EVT_TYPE`), responding units, and linked pipeline events.
  - **General Entity Aggregations** (e.g. *"What units were most active this afternoon?"*, *"What were the top call types today?"*):
    - Agent invokes `lookup_ner_entities(label="UNIT")` or `lookup_ner_entities(label="EVT_TYPE")` without a specific search query.
    - Returns top entity frequency counts with earliest and latest timestamps in scope.
- **Backend Service Implementation** ([`app/services/agent_tools.py`](file:///a:/Scanscribe_Projects/scanscribe/app/services/agent_tools.py)):
  - Create `execute_lookup_ner_entities(db, query, label, talkgroup, start_time, end_time, limit)`:
    - Queries `EntityObservation` joined with `LogEntry` (and `EventTranscriptLink` / `Event` where available) to give the LLM full situational context in a single call.
    - Formats each occurrence with:
      - `[TX-<id>]` citation token
      - Dual timestamp (12h AM/PM and 24h military)
      - Talkgroup channel
      - Entity label (`UNIT`, `LOC`, `ADDRESS`, `EVT_TYPE`, `STATUS`) and canonical normalized name
      - Transmission transcript excerpt
      - Linked event summary (if attached to a detected incident)
- **Tool Schema Registration** ([`app/services/agent_tools.py`](file:///a:/Scanscribe_Projects/scanscribe/app/services/agent_tools.py)):
  - Register `LOOKUP_NER_ENTITIES_DECLARATION` for Google Gemini function calling.
  - Register OpenAI/OpenRouter compatible schema in `AGENT_TOOLS_OPENAI`.
  - Add to `TOOL_EXECUTORS` dispatch mapping.
- **Agent Rules & Guidance** ([`app/services/chat_context.py`](file:///a:/Scanscribe_Projects/scanscribe/app/services/chat_context.py)):
  - Add explicit protocol rules directing the agent to use `lookup_ner_entities` as its primary tool for questions regarding specific emergency units (e.g. *"What did unit 112 do?"*) or specific street addresses/locations (e.g. *"What happened at 1155 walton dr?"*), instructing it to synthesize a clear chronological timeline of events citing `[TX-<id>]`.
- **Unit Tests** ([`tests/test_agent_tools.py`](file:///a:/Scanscribe_Projects/scanscribe/tests/test_agent_tools.py)):
  - Test unit query timeline retrieval, address lookups, label filtering, and frequency aggregations.

---

### Phase 3: Dedicated Right-Side Audio Control Panel
- **New Component**: [`app/frontend/src/pages/Intel/components/AudioControlPanel.tsx`](file:///a:/Scanscribe_Projects/scanscribe/app/frontend/src/pages/Intel/components/AudioControlPanel.tsx)
  - **Header**:
    - Title: "Transmission Audio" with total cited clips badge.
    - Continuous play toggle ("Auto-Advance").
    - Close / collapse button.
  - **Active Player Station**:
    - Custom styled playback bar utilizing HTML5 audio and/or canvas waveform peaks (similar to ScanScribe's `ScAudioPlayer` architecture).
    - Scrubbing seeker with smooth dragging, progress filling (`bg-indigo-500` / `bg-sky-500`), and buffered ranges.
    - Time readouts: Current position / Total duration (`0:03 / 0:12`).
    - Core Controls:
      - Skip Back 5s (`-5s`).
      - Play / Pause button (large tactical button with play/pause icons).
      - Skip Forward 5s (`+5s`).
      - Playback Speed toggle (`1.0x`, `1.25x`, `1.5x`, `2.0x`).
      - Volume slider with mute button.
  - **Cited Clips Queue**:
    - Chronologically sorted list of all transmissions cited in the active thread (or current assistant message).
    - Each card displays:
      - `TX #<id>` badge with click-to-play.
      - Talkgroup pill with color coding.
      - Formatted local time (12h AM/PM with 24h military indicator) and duration.
      - Verbatim recorded transcript text with phonetic fallibility warning badge if low confidence.
      - Active playing status pulse animation when currently playing.
  - **Continuous Playback**:
    - When an audio clip finishes (`onEnded`), if "Auto-Advance" is enabled, automatically select and play the next cited clip in the list.
- **Layout Integration in [`IntelPage.tsx`](file:///a:/Scanscribe_Projects/scanscribe/app/frontend/src/pages/Intel/IntelPage.tsx)**:
  - Flexbox layout: Left thread drawer + Main conversation column + Right Audio Control Panel.
  - Right panel width: `w-80` to `w-96` on desktop (`lg:flex`), collapsible slide-out drawer on smaller viewports.
  - Auto-open right panel when operator clicks any `[TX #...]` badge or when an assistant response finishes containing citations.

---

### Phase 4: ChatGPT-Style Layout Migration
- **Refactor [`ChatMessageList.tsx`](file:///a:/Scanscribe_Projects/scanscribe/app/frontend/src/pages/Intel/components/ChatMessageList.tsx)**:
  - Eliminate the right-aligned vs left-aligned SMS chat bubbles:
    - User prompts: Full-width row with centered `max-w-3xl` container. Subtle dark background (`bg-[#131622]/60` or transparent border), user avatar icon (`Operator`), crisp white text.
    - Assistant responses: Full-width row with centered `max-w-3xl` container. ScanScribe Intel badge/icon, seamless document typography.
  - Clean separation:
    - Thinking accordion cleanly integrated into the header of assistant responses without bubble margins.
    - Tool call cards positioned natively in the response stream.
    - Markdown content rendered with rich typography (headings, clean code blocks, styled lists, blockquotes).
  - Response Action Bar:
    - Quick Copy button (copies assistant text to clipboard with "Copied!" feedback).
    - "Play Cited Audio (N)" button that focuses the right-side audio panel.
- **Refactor [`ChatInputBox.tsx`](file:///a:/Scanscribe_Projects/scanscribe/app/frontend/src/pages/Intel/components/ChatInputBox.tsx)**:
  - Center within `max-w-3xl mx-auto`.
  - Floating rounded container (`rounded-2xl` or `rounded-xl`) with subtle border `border-[#262b3d]` and glow focus.
  - Auto-expanding multiline textarea (up to 200px max height).
  - Integrated right-side Send / Stop generating button with keyboard shortcut tooltip (`Enter` to send, `Shift+Enter` for newline).

---

### Phase 5: State Management & Transmission Synchronization
- **State Flow in [`IntelPage.tsx`](file:///a:/Scanscribe_Projects/scanscribe/app/frontend/src/pages/Intel/IntelPage.tsx)**:
  - Extract cited IDs from all messages in the active thread:
    - Aggregate transmission IDs cited across messages (`txIds = extractCitedTxIds(messages)`).
    - Pre-fetch or on-demand fetch transmission metadata via `chatApi.getTransmission(txId)` so the right panel can display talkgroup, timestamp, and transcript without delay.
  - Active audio state:
    - `activeTxId: number | null`
    - `isPlaying: boolean`
    - `audioPanelOpen: boolean` (persisted or toggleable via button in TimeScopeBar).
  - When operator clicks `[TX #12345]`:
    - `setAudioPanelOpen(true)`
    - `setActiveTxId(12345)`
    - Audio begins playing immediately.

---

### Phase 6: Verification & Safety Gates
1. **Audio Web APIs Audit**:
   - Verify proper Audio element teardown on unmount or track switch (preventing memory leaks or audio playback overlaps per `audio-web-apis` skill).
   - Catch and handle `play()` promise rejections (`AbortError`).
2. **Tailwind & Responsive Audit**:
   - Check mobile layout (sliding drawer for audio control) and desktop layout (`100dvh`, clean scrolling independent between chat and audio panel).
3. **Build & Test Validation**:
   - Run `cd app/frontend && npm run typecheck`
   - Run `cd app/frontend && npm run build`
   - Run `python -m pytest tests/`
   - Verify live station server on `http://localhost:8000/app/intel`.
