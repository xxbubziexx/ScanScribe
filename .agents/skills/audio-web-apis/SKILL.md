---
name: audio-web-apis
description: >-
  Audits and guides Web Audio API and HTML5 Audio implementations, AudioContext
  lifecycle management, browser autoplay policies, waveform visualization,
  streaming buffers, and memory leak prevention in web applications.
---

# Audio Web APIs Skill

This skill provides design patterns, debugging procedures, and audit checklists for Web Audio API (`AudioContext`, `AnalyserNode`, `GainNode`) and HTML5 Audio (`<audio>`, `Audio()` element) in browser applications, especially focused on radio/voice stream playback and waveform rendering.

## When to Run This Skill
- The user requests an audit of web audio players, streaming monitors, or waveform visualizers.
- Diagnosing audio glitches, playback errors, browser autoplay rejections, or memory leaks caused by retained audio nodes.
- Implementing or refactoring audio player components, live radio stream listeners, or canvas-based audio visualizers.

---

## Core Audio Principles & Pitfalls

### 1. `AudioContext` Lifecycle & Limits
- **Browser Context Limits:** Browsers limit active `AudioContext` instances per tab (typically 6 maximum in Chrome/WebKit). Creating a new `new AudioContext()` per player component quickly exhausts the limit, throwing errors.
  - *Fix:* Use a shared singleton `AudioContext` or ensure explicit `.close()` on unmount.
- **Suspended State & Autoplay Policy:** Browsers initialize `AudioContext` in `'suspended'` state until user gesture (click/keypress).
  - *Fix:* Always check `ctx.state === 'suspended'` and call `await ctx.resume()` on user interaction prior to playback.

### 2. Audio Element Memory Leaks & Event Cleanup
- **Zombie `<audio>` Elements:** Re-instantiating `new Audio(src)` without tearing down previous instances retains audio decoding buffers in memory.
  - *Fix:* Clean up in React `useEffect` unmount:
    ```javascript
    audio.pause();
    audio.removeAttribute('src'); // or audio.src = '';
    audio.load();
    // remove all attached event listeners (timeupdate, ended, error)
    ```

### 3. Waveform & Canvas Animation Loops
- **Uncontrolled `requestAnimationFrame`:** Animation loops polling audio state without cancellation when playback stops or components unmount cause high CPU utilization and battery drain.
  - *Fix:* Store animation frame ID (`rafId = requestAnimationFrame(...)`) and cancel with `cancelAnimationFrame(rafId)` when audio is paused or unmounted.

### 4. Audio Buffering & Streaming Race Conditions
- **Rapid Track Switching:** Rapidly changing audio tracks while playback is buffering can result in playback overlap or uncaught `AbortError: The play() request was interrupted by a new load request.`
  - *Fix:* Safely handle the promise returned by `audio.play()`:
    ```javascript
    const playPromise = audio.play();
    if (playPromise !== undefined) {
      playPromise.catch((err) => {
        if (err.name !== 'AbortError') {
          console.error('Audio playback error:', err);
        }
      });
    }
    ```

---

## Step-by-Step Audit Procedure

### Step 1: Component Audio Lifecycle Audit
1. Locate all audio player components (e.g. `ScAudioPlayer.tsx`, dataset player, live stream player).
2. Verify cleanup in `useEffect` return functions:
   - Are audio instances paused and detached?
   - Are DOM event listeners cleanly removed?
   - Are visualizer intervals / `requestAnimationFrame` IDs cancelled?

### Step 2: Autoplay & User Interaction Audit
1. Test audio playback initiation against modern browser autoplay policy.
2. Confirm user feedback (visual play/pause indicator, volume sliders, mute toggle) is in sync with actual audio state.

### Step 3: Waveform Visualization Audit
1. Check canvas resolution and Retina/HiDPI scaling (`window.devicePixelRatio`).
2. Verify visualizer does not re-render when audio is paused or stopped.
3. Check audio source decoding (e.g. `AudioContext.decodeAudioData` error handling on truncated or corrupt audio files).

### Step 4: Verification Checks
1. Type check:
   ```bash
   cd app/frontend && npm run typecheck
   ```
2. Unit tests:
   ```bash
   cd app/frontend && npm test
   ```
