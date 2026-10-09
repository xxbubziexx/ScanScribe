# Phase 5: Frontend Component Decomposition & Bundle Optimization

> **Phase Order**: 5 of 5  
> **Status**: Ready for Implementation  
> **Estimated Execution Time**: ~2–3 hours  
> **Target Files**: `app/frontend/src/pages/`, `app/frontend/src/components/`, `app/frontend/vite.config.ts`, `app/frontend/src/styles/`

---

## 1. Objectives

1. Decompose massive React page components (such as [`IncidentsPage.tsx`](file:///a:/Scanscribe_Projects/scanscribe/app/frontend/src/pages/Events/IncidentsPage.tsx) at 1,109 lines) into modular, reusable UI components.
2. Optimize the production build bundle size from **5.4MB down to < 1.5MB** by eliminating unnecessary Monaco Editor language bundles (MIPS, Pascal, Fortran, etc.).
3. Lazy-load heavy dependencies (Leaflet maps, Monaco editor) via `React.lazy()` code-splitting.
4. Consolidate the hybrid styling mess by integrating custom `ss-` classes into Tailwind CSS v4 design tokens.
5. Standardize TypeScript contracts between backend Pydantic schemas and frontend interfaces.

---

## 2. Decomposing Monolithic React Pages

### 1. [`IncidentsPage.tsx`](file:///a:/Scanscribe_Projects/scanscribe/app/frontend/src/pages/Events/IncidentsPage.tsx) (1,109 lines)
Decompose into a dedicated feature directory:

```
app/frontend/src/pages/Events/Incidents/
├── index.tsx                     # Main layout & route component (~150 lines)
├── hooks/
│   ├── useIncidentsQuery.ts      # TanStack Query & WebSocket subscription (~100 lines)
│   └── useIncidentActions.ts    # Mutations (close, reopen, edit, summarize) (~90 lines)
├── components/
│   ├── IncidentFeed.tsx          # Card feed with virtual scrolling / grid (~180 lines)
│   ├── IncidentCard.tsx          # Incident presentation card with timers (~150 lines)
│   ├── IncidentDetailModal.tsx   # Modal for transcript thread & timeline (~200 lines)
│   ├── IncidentEditModal.tsx     # Form for manual classification & location (~120 lines)
│   └── IncidentFilterBar.tsx     # Monitor, status, and talkgroup filters (~100 lines)
└── utils/
    ├── formatters.ts             # Time relative/countdown formatting (~60 lines)
    └── incidentBadges.ts         # Priority, broadcast, and unit tags (~50 lines)
```

### 2. [`DatabasePage.tsx`](file:///a:/Scanscribe_Projects/scanscribe/app/frontend/src/pages/Database/DatabasePage.tsx) (822 lines)
Extract reusable data table primitives into `src/components/common/table/`:
* `DataTableHeader.tsx`: Column sort toggles, selection checkboxes.
* `DataTablePagination.tsx`: Page size selector, jump-to-page controls.
* `DataTableRowDetail.tsx`: Expandable audio player & full transcript inspector.

---

## 3. Monaco Editor Bundle Optimization (5.4MB ➔ < 1.5MB)

### The Problem:
`app/frontend/dist/assets/` currently contains 97 generated script chunks totaling ~5.4MB because importing `monaco-editor` defaults to bundling syntax highlighters for dozens of unused languages (e.g. `objective-c`, `julia`, `pascaligo`, `mips`, `powerquery`).

### The Solution:
1. **Lazy Load Monaco**: Only load the Monaco bundle when the user actually accesses the Settings page (`SettingsPage.tsx`):
```tsx
// app/frontend/src/App.tsx
import { lazy, Suspense } from 'react'

const SettingsPage = lazy(() => import('./pages/Settings/SettingsPage'))

// Wrap route in Suspense:
<Route path="/settings" element={
  <Suspense fallback={<div className="p-8 text-center text-gray-400">Loading editor...</div>}>
    <SettingsPage />
  </Suspense>
} />
```

2. **Restrict Monaco Languages in `vite.config.ts`**:
Configure Monaco or `@monaco-editor/react` to import strictly the core editor with `yaml` and `json` support:
```ts
// app/frontend/vite.config.ts
export default defineConfig({
  // ...
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'monaco-core': ['monaco-editor/esm/vs/editor/editor.api'],
          'leaflet-vendor': ['leaflet', 'react-leaflet'],
          'charts-vendor': ['recharts'],
        },
      },
    },
  },
})
```

---

## 4. Styling Consolidation: Tailwind v4 + Design Tokens

### The Current Conflict:
The project loads Tailwind v4 (`@tailwindcss/vite`), but also includes 11 bespoke CSS files in `src/styles/components/` that hardcode duplicate rules using `.ss-` class selectors.

### The Unified Design System:
Consolidate component styles into [`app/frontend/src/index.css`](file:///a:/Scanscribe_Projects/scanscribe/app/frontend/src/index.css) using Tailwind v4 theme directives and reusable component classes:

```css
@import "tailwindcss";

@layer components {
  /* Reusable button styles replacing manual CSS files */
  .ss-btn-primary {
    @apply inline-flex items-center justify-center px-3 py-1.5 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-500 rounded-md shadow-xs transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed;
  }
  
  .ss-btn-ghost {
    @apply inline-flex items-center justify-center px-3 py-1.5 text-sm font-medium text-gray-300 hover:text-white hover:bg-gray-800 rounded-md transition-colors duration-150;
  }

  .ss-card {
    @apply bg-gray-900 border border-gray-800 rounded-lg p-4 shadow-sm;
  }

  .ss-input {
    @apply bg-gray-950 border border-gray-800 rounded-md px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:outline-hidden focus:border-indigo-500 transition-colors;
  }
}
```

Delete redundant files in `src/styles/components/` once migrated.

---

## 5. Type Contract Synchronization

Ensure TypeScript models in `src/types/` exactly mirror backend Pydantic schemas:

```typescript
// app/frontend/src/types/events.ts
export interface EventModel {
  id: number
  eventId: string
  monitorId: number
  status: 'open' | 'closed'
  eventType: string | null
  broadcastType: string | null
  location: string | null
  latitude: number | null
  longitude: number | null
  resolvedAddress: string | null
  units: string[]  // Strictly typed array, never raw string
  statusDetail: string | null
  summary: string | null
  createdAt: string
  updatedAt: string
  closedAt: string | null
}
```

---

## 6. Verification Criteria

- [ ] `npm run build` completes in `< 30s` with a total bundle size `< 2.0MB` (down from 5.4MB).
- [ ] No single `.tsx` file exceeds **350 lines**.
- [ ] `npm run typecheck` (`tsc -b --noEmit`) passes with zero type errors.
- [ ] `npm run test` executes all frontend tests cleanly via Vitest.
- [ ] Audio playback, live incident WebSocket updates, and map markers render with zero visual regressions.
