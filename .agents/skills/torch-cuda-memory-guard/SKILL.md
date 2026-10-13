---
name: torch-cuda-memory-guard
description: >-
  Audits and enforces PyTorch CUDA memory management, VRAM leak prevention,
  tensor device tracking, half-precision (fp16/bf16) inference, explicit cache cleanup,
  and graceful CPU fallback.
---

# PyTorch CUDA Memory Guard Skill

This skill provides guidelines, auditing procedures, and memory protection runbooks for PyTorch models (Whisper, RoBERTa/DeBERTa NER, Silero VAD) running in continuous inference services.

## When to Run This Skill
- The user requests an audit of PyTorch or CUDA memory usage.
- Investigating `CUDA out of memory` (OOM) errors, GPU VRAM creeping upwards over time, or slow GPU inference throughput.
- Integrating or upgrading deep learning models (ASR, token classification, VAD).

---

## Core CUDA Memory Guard Principles

### 1. Zero Gradient Tracking During Inference
- **Rule:** Never execute forward passes without inference mode or no-grad.
  - Preferred: `with torch.inference_mode():` (more performant than `torch.no_grad()`, disables view tracking and version counting).
  - Also ensure `model.eval()` is called once after loading.

### 2. Half-Precision (FP16 / BF16) on CUDA
- **Rule:** When running on CUDA GPUs (Turing/Ampere/Ada/Hopper or newer), load models with `torch_dtype=torch.float16` or `torch.bfloat16`.
- **Impact:** Cuts VRAM consumption by ~50% (e.g. Whisper-small from ~1.9GB to ~950MB) and significantly accelerates Tensor Core execution.
- **CPU Safety:** On CPU, keep FP32 (`torch.float32`) or use bfloat16 only if AVX-512 VNNI/AMX is supported.

### 3. Preventing Tensor Retention & Accumulation
- **Rule:** Never store intermediate PyTorch tensors in long-lived lists, dicts, or global state.
  - If numerical metrics or scores are needed, extract Python primitives immediately: `loss.item()`, `score.detach().cpu().item()`.
  - When batching chunks in a loop, explicitly delete large intermediate tensors or let them fall out of scope:
    ```python
    del input_features, generated_ids
    ```

### 4. Periodic & Exceptional Cache Reclamation
- **Rule:** PyTorch's caching allocator holds reserved VRAM even after tensors are freed.
  - In long-running services, after processing unusually large batches or encountering an exception:
    ```python
    import gc
    import torch

    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    ```
- **OOM Catching & Graceful Recovery:**
  ```python
  except torch.cuda.OutOfMemoryError as oom:
      logger.error("CUDA OOM detected! Purging cache and attempting fallback...")
      gc.collect()
      torch.cuda.empty_cache()
      # Fallback to smaller chunk or CPU if needed
  ```

### 5. Multi-Model GPU Sharing & Contention
- In systems running both Whisper ASR and NER simultaneously on a single GPU:
  - Account for combined VRAM: ensure total weights and peak activation memory fit comfortably within device VRAM limit (e.g. 4GB or 6GB budget on edge nodes).
  - Avoid competing CUDA streams that exhaust allocator blocks simultaneously.

---

## Step-by-Step Audit Procedure

### Step 1: Model Loading & Precision Audit
1. Inspect `app/services/transcription_engine.py` and `app/services/ner_service.py`.
2. Check `torch_dtype` on `from_pretrained()` and pipeline creation.
3. Verify `model.eval()` is called.
4. Verify CPU vs CUDA fallback logic.

### Step 2: Forward Pass & Tensor Lifecycle Audit
1. Verify `torch.inference_mode()` or `torch.no_grad()` surrounds all forward/generate calls.
2. Check chunk loops for accumulation of tensor objects.
3. Ensure `.to(device)` targets match model device and precision.

### Step 3: Cleanup & Error Recovery Audit
1. Check for `torch.cuda.empty_cache()` on teardown or model reload.
2. Verify exception handling handles `torch.cuda.OutOfMemoryError`.

### Step 4: Verification Checks
1. Run backend tests:
   ```bash
   pytest tests/
   ```
