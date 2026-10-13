---
name: tailwind-component-patterns
description: >-
  Audits and enforces Tailwind CSS design system patterns, tactical emergency
  dark mode palettes, component tokens, typography scales, accessibility contrasts,
  and elimination of arbitrary styling anti-patterns.
---

# Tailwind Component Patterns Skill

This skill provides architectural guidelines, design token definitions, and audit procedures for Tailwind CSS (v3 and v4) implementations in mission-critical tactical applications like ScanScribe.

## When to Run This Skill
- The user requests an audit of Tailwind CSS styling, UI component design, or layout responsiveness.
- Reviewing UI components for dark mode contrast, consistent design tokens, and tactical public-safety aesthetics.
- Refactoring inconsistent styles, redundant class strings, or arbitrary pixel values into clean, composable component patterns.

---

## Core Design System Rules

### 1. Tactical Dark Mode Theme Palette
Public safety command centers require high-contrast, low-eyestrain tactical dark palettes:
- **Surface & Backgrounds:**
  - Base Background: `bg-slate-950` / `bg-zinc-950`
  - Elevated Cards/Panels: `bg-slate-900/90` or `bg-zinc-900/90` with subtle border `border-slate-800`
  - Input & Control Wells: `bg-slate-800/60`
- **Semantic Priority / Status Colors:**
  - Critical / Priority 1: Red / Crimson (`text-rose-400`, `bg-rose-950/40`, `border-rose-800/60`)
  - Warning / Priority 2: Amber / Orange (`text-amber-400`, `bg-amber-950/40`, `border-amber-800/60`)
  - Informational / Routine: Blue / Sky (`text-sky-400`, `bg-sky-950/40`, `border-sky-800/60`)
  - Healthy / Active / On Scene: Emerald / Green (`text-emerald-400`, `bg-emerald-950/40`, `border-emerald-800/60`)
  - Muted / Inactive: Slate / Zinc (`text-slate-400`, `text-slate-500`)

### 2. Component Composition & Utility Hygiene
- **Avoid Arbitrary Value Sprawl:** Avoid one-off arbitrary values like `w-[347px]`, `text-[13px]`, `top-[17px]` unless mathematically required for canvas/chart alignment. Use standard Tailwind scale (`w-80`, `text-xs`, `text-sm`, `top-4`).
- **Composable Class Merging:** When writing customizable React components with dynamic class names, use `clsx` and `tailwind-merge` (or standard template literals) to prevent conflicting CSS rule overrides.
- **Micro-Animations & Transitions:** Tactical interfaces must feel alive yet snappy. Use subtle transitions (`transition-colors duration-150`, `ease-out`) for hover, active states, and focus rings.

### 3. Accessibility & Hit Target Standards
- **Focus Rings:** Ensure all interactive elements have visible focus rings for keyboard operators:
  `focus:outline-none focus:ring-2 focus:ring-sky-500 focus:ring-offset-2 focus:ring-offset-slate-950`
- **Touch Targets:** Minimum target area of 40x40px (desktop) and 44x44px (mobile touch).

---

## Step-by-Step Audit Procedure

### Step 1: Design System & Color Palette Audit
1. Inspect `app/frontend/src/styles/` and CSS token definitions.
2. Check for inconsistent color usage across components (e.g. mixing `gray`, `zinc`, `neutral`, `slate`).
3. Ensure status colors (priority badges, unit status chips) conform to standard semantic tokens.

### Step 2: Component Refactoring Audit
1. Scan for long duplicated class strings across multiple `.tsx` files.
2. Identify reusable primitives that should be extracted into shared components (`Badge`, `Button`, `Card`, `Modal`).
3. Verify that Tailwind v4 imports (`@import "tailwindcss";`) and theme variables are correctly configured.

### Step 3: Verification Checks
1. Run linter and formatting:
   ```bash
   cd app/frontend && npm run lint
   ```
2. Build validation:
   ```bash
   cd app/frontend && npm run build
   ```
