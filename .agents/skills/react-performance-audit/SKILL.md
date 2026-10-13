---
name: react-performance-audit
description: >-
  Audits and optimizes React frontend performance, component rendering cycles,
  state colocation, memoization hygiene, virtualized lists for high-frequency
  streaming data, WebSocket state thrashing, and bundle size.
---

# React Performance Audit Skill

This skill provides a comprehensive runbook and checklist for auditing and optimizing React applications, specifically tailored for high-throughput real-time dashboards and command centers (such as ScanScribe).

## When to Run This Skill
- The user requests a React performance audit or frontend optimization.
- Live streaming feeds, WebSocket updates, or audio logs cause UI stutter, frame drops, or high CPU usage.
- High-frequency data (e.g. real-time radio events, map markers, log entries) triggers excessive re-renders.
- Investigating frontend bundle sizes, memory leaks, or slow initial page loads.

---

## Core Performance Checklists & Anti-Patterns

### 1. Re-render Cascades & Context Thrashing
- **Root-level Context Thrashing:** Pushing high-frequency WebSocket events directly into a top-level React Context forces every consumer component to re-render.
  - *Fix:* Split contexts into static/infrequent (auth, config, theme) and high-frequency streaming (events, audio telemetry). Use dedicated stores (e.g., Zustand, external stores with `useSyncExternalStore`) or selective subscriptions.
- **Inline Object & Function Recreation:** Passing inline callbacks `() => handleClick(id)` or fresh object literals `style={{ ... }}` into memoized child components breaks `React.memo` and triggers re-renders.
  - *Fix:* Wrap event handlers in `useCallback` and computed objects/arrays in `useMemo`.

### 2. Large Collections & Stream Virtualization
- **Unbounded DOM Elements:** Rendering hundreds of log rows, incident cards, or chat items directly in the DOM degrades scroll performance and memory.
  - *Fix:* Implement windowing/virtualization (e.g., TanStack Virtual / `react-window`) for feeds exceeding 50 items.
  - *Fix:* Keep DOM node count under 1,500 nodes per view.

### 3. Geospatial / Map Render Bottlenecks (Leaflet / Mapbox)
- **Marker Re-creation:** Re-mounting Leaflet marker layers or polyline layers on every state update freezes the main thread.
  - *Fix:* Use stable marker keys and update coordinates imperatively or through memoized marker collections rather than tearing down and rebuilding layers.

### 4. Dependency Array Hygiene
- **Stale Closures & Overactive Effects:** Missing dependencies cause subtle bugs; bloated dependency arrays cause infinite loops or effect thrashing.
  - *Fix:* Verify ESLint `react-hooks/exhaustive-deps` rules. Avoid referencing entire complex objects inside `useEffect` deps; extract primitive IDs or flags.

### 5. Bundle Size & Code Splitting
- **Heavy Third-Party Libraries:** Loading Monaco Editor, charting libraries (Recharts), or large map libraries upfront inflates initial bundle.
  - *Fix:* Use `React.lazy()` and `Suspense` for heavy routes (Data Explorer, Settings, Insights) and modal-based editors.

---

## Step-by-Step Audit Procedure

### Step 1: Component Hierarchy & Render Profiling
1. Identify components that re-render upon WebSocket messages.
2. Check if parent components pass unstable props (new arrays, new functions) to children.
3. Verify that list items have stable, unique keys (never use array index for items that can reorder, filter, or prepend).

### Step 2: Memoization & Hook Hygiene
1. Audit expensive computation paths (e.g., sorting, filtering, aggregations over hundreds of entries) for missing `useMemo`.
2. Audit callbacks passed down multiple component tiers for missing `useCallback`.
3. Check `React.memo` usage on leaf components within high-frequency lists.

### Step 3: Streaming State Management Audit
1. Audit WebSocket hooks (`useWebSocket`). Check how incoming messages are buffered.
2. Ensure batching of high-frequency events (e.g., throttling incoming messages to requestAnimationFrame or micro-batches) so React isn't scheduling render passes for every millisecond packet.

### Step 4: Verification & Benchmarking
1. Run TypeScript check:
   ```bash
   cd app/frontend && npm run typecheck
   ```
2. Run linter and tests:
   ```bash
   cd app/frontend && npm run lint
   npm test
   ```
3. Check production build output and bundle chunks:
   ```bash
   cd app/frontend && npm run build
   ```
