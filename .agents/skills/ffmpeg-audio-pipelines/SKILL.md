---
name: ffmpeg-audio-pipelines
description: >-
  Audits and optimizes FFmpeg audio processing pipelines, non-blocking subprocess
  execution, streaming pipe I/O without deadlocks, audio normalization, format
  conversion, and temporary file lifecycle safety.
---

# FFmpeg Audio Pipelines Skill

This skill provides architectural rules, pipeline templates, and audit procedures for FFmpeg and audio decoding/transcoding workflows in high-reliability public safety systems.

## When to Run This Skill
- The user requests an audit of audio conversion, ingest pipelines, or FFmpeg commands.
- Investigating process hangs, zombie subprocesses, pipe buffer deadlocks, or disk bloat from temporary WAV/MP3 files.
- Implementing audio normalization (`loudnorm`/`dynaudnorm`), resampling to 16kHz mono for Whisper/VAD, or stream slicing.

---

## Core FFmpeg Pipeline Rules

### 1. Non-Blocking Subprocess Execution
- **Deadlock Warning:** Calling synchronous `subprocess.run(..., stdout=subprocess.PIPE, stderr=subprocess.PIPE)` inside an asyncio event loop blocks the entire server. Furthermore, if FFmpeg produces more than 64KB of log output, the OS pipe buffer fills up and permanently deadlocks the process.
- **Asynchronous Pattern:**
  ```python
  import asyncio

  proc = await asyncio.create_subprocess_exec(
      "ffmpeg", *args,
      stdout=asyncio.subprocess.PIPE,
      stderr=asyncio.subprocess.PIPE
  )
  stdout, stderr = await proc.communicate()
  if proc.returncode != 0:
      logger.error("FFmpeg error (code %d): %s", proc.returncode, stderr.decode(errors="replace"))
  ```
- **Threadpool Alternative:** If using synchronous Python wrappers (e.g. `soundfile`, `librosa`), always wrap with `await asyncio.to_thread(...)`.

### 2. Standard Audio Profile for Public Safety ASR & VAD
Whisper and Silero VAD require 16kHz, single-channel (mono), 16-bit PCM:
- **Resampling & Downmixing:**
  ```bash
  ffmpeg -y -i input.m4a -ar 16000 -ac 1 -c:a pcm_s16le output.wav
  ```
- **Dynamic Normalization for Police/Fire Radio:**
  Radio dispatchers and field units often have drastically different microphone volumes:
  ```bash
  -af "dynaudnorm=f=150:g=15"
  # or two-pass loudnorm:
  -af "loudnorm=I=-16:TP=-1.5:LRA=11"
  ```

### 3. Safe Temporary File Handling
- **Windows File Locking:** On Windows, attempting to delete an open file raises `PermissionError: [WinError 32] The process cannot access the file because it is being used by another process`.
  - Always close file descriptors before passing filenames to external processes:
    ```python
    fd, temp_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        # process temp_path
    finally:
        if os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass
    ```

### 4. Handling Corrupted or Incomplete Ingest Audio
- SDR receivers and Trunk Recorder occasionally produce truncated or corrupted audio chunks.
- Audio loaders must cleanly catch decode exceptions and not crash the worker loop.

---

## Step-by-Step Audit Procedure

### Step 1: Subprocess & Audio Loading Audit
1. Inspect audio loading routines in `app/services/transcription_engine.py`, `app/services/watcher.py`, and `app/utils/audio_metadata.py`.
2. Check for blocking subprocess calls or unhandled pipe buffers.
3. Verify all file operations are wrapped asynchronously (`asyncio.to_thread`).

### Step 2: Sample Rate & Channel Normalization Audit
1. Ensure audio passed to Whisper and Silero VAD is converted to 16,000 Hz mono.
2. Check if silence removal or VAD slicing retains valid headers and metadata.

### Step 3: Temp File Cleanup & Leak Audit
1. Search for `tempfile.mkstemp` and `tempfile.NamedTemporaryFile` calls.
2. Confirm every temporary file is guaranteed to be deleted in a `finally` block or context manager.

### Step 4: Verification Checks
1. Run backend tests:
   ```bash
   pytest tests/
   ```
