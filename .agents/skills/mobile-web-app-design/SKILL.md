---
name: mobile-web-app-design
description: >-
  Audits and optimizes mobile web ergonomics for tactical dispatch and incident
  field responders, responsive layouts, touch target dimensions, dynamic viewport
  heights (100dvh), and mobile drawer/bottom-sheet usability.
---

# Mobile Web App Design Skill

This skill provides mobile ergonomics principles, responsive layout architectures, and audit procedures for mission-critical web applications used on phones and tablets in the field.

## When to Run This Skill
- The user requests an audit of mobile responsiveness, touch UX, or mobile-first layouts.
- Reviewing incident maps, command center feeds, or audio player controls on mobile devices.
- Fixing mobile layout bugs (scrolling jitter, iOS Safari viewport height jumping, awkward touch targets).

---

## Tactical Mobile Design Principles

### 1. Viewport & Safe Area Resilience
- **Meta Viewport Configuration:**
  Ensure `index.html` specifies:
  ```html
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover" />
  ```
- **Dynamic Viewport Height (`100dvh`):**
  On mobile browsers (iOS Safari / Chrome Android), `100vh` causes content to be cut off by disappearing/appearing URL toolbars. Use `h-[100dvh]` or `min-h-[100dvh]` for full-screen dashboards.
- **Safe Area Insets:**
  Respect device home indicator bars and camera notches:
  ```css
  padding-bottom: env(safe-area-inset-bottom, 1rem);
  padding-top: env(safe-area-inset-top, 0.5rem);
  ```

### 2. Touch Targets & Ergonomics
- **Minimum Hit Area:** Touch targets for buttons, play toggles, navigation tabs, and map markers must be at least 44x44px (recommended: 48x48px) to accommodate gloved hands and rapid field interaction.
- **Thumb-Zone Navigation:** Place critical controls (feed filters, play/pause, drawer toggles) in the bottom screen quadrant (thumb zone) rather than top corners.

### 3. Responsive Map & Split-Pane Layouts
- **Desktop vs Mobile Command Center:**
  - On desktop (`lg:`): Side-by-side split screen (live incident map on left/right, live audio feed on other half).
  - On mobile (`< lg:`): Tabbed or bottom-sheet layout (full-screen map with swipeable/collapsible bottom sheet for incident cards, or a bottom navigation bar switching between Map, Feed, and Logs).

### 4. Mobile Audio & Media Playback
- **Autoplay Handling:** Mobile browsers strictly block audio without an explicit user touch interaction. Display an intuitive "Tap to Listen / Start Monitor" activation badge if the feed is live.
- **Audio Scrubber:** Ensure waveform or scrub bars have thick touch-draggable handles on touch devices.

---

## Step-by-Step Audit Procedure

### Step 1: Viewport & Layout Meta Audit
1. Inspect `app/frontend/index.html` for viewport meta configuration.
2. Inspect `App.tsx` and layout roots for `h-screen` vs `h-[100dvh]`.
3. Check safe-area inset support in bottom navigation and fixed headers.

### Step 2: Touch Target Audit
1. Review buttons, audio player controls, and table actions across mobile views.
2. Check for cramped clickable elements smaller than 44px.

### Step 3: Responsive Breakpoints & Drawer Audit
1. Inspect `CommandCenterPage.tsx` and `TopNav.tsx` at mobile breakpoints (`< 768px`).
2. Verify drawer/navigation menus close cleanly on route navigation.
3. Check that Leaflet maps resize correctly on mobile orientation changes (`map.invalidateSize()`).

### Step 4: Verification Checks
1. Run frontend tests:
   ```bash
   cd app/frontend && npm test
   ```
2. Build check:
   ```bash
   cd app/frontend && npm run build
   ```
