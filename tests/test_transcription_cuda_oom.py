"""Regression tests for CUDA OOM handling in the transcription engine.

Background / root cause
-----------------------
Whisper's `generate()` allocates the KV cache for every beam plus, when
`output_scores=True`, a `[beams, vocab]` logit tensor for *every* decode step.
On a small-VRAM GPU that peak allocation can exceed the device budget, and CUDA
reports the resulting OOM **asynchronously** — at a later CUDA call, often after
`generate()` itself has already returned.

Two consequences are covered here:

1. The OOM is observed outside the engine's own `try/except`, so
   `torch.cuda.empty_cache()` never ran. The allocator kept its reserved blocks,
   the next file OOM'd immediately, and the whole ingest pipeline wedged.
2. Nothing reduced the memory footprint after an OOM, so the engine never
   self-healed: beam search was retried with identical (too-large) settings.

These tests run with `torch` mocked (see conftest.py), so they are deterministic
and need no GPU.
"""
import asyncio
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.services.transcription_engine import (
    TranscriptionEngine,
    TranscriptionOutOfMemoryError,
    is_cuda_oom_error,
)

OOM_MESSAGE = (
    "CUDA error: out of memory CUDA kernel errors might be asynchronously "
    "reported at some other API call, so the stacktrace below might be incorrect."
)


def _make_engine(beam_size=5):
    """Engine wired to mocked torch/transformers with a CUDA device selected."""
    engine = TranscriptionEngine()
    engine.device = "cuda"
    engine.is_english_only = True
    engine.config.transcription.beam_size = beam_size

    engine.model = MagicMock()
    engine.model.dtype = "float16"

    processor = MagicMock()
    processor.return_value.input_features.to.return_value = "features"
    processor.batch_decode.return_value = ["hello"]
    engine.processor = processor
    return engine


def _ok_generate_result():
    """Beam-search style result: sequences_scores present, no per-step scores."""
    result = MagicMock()
    result.sequences = "seq"
    result.sequences_scores = None
    result.scores = []
    return result


def _patch_audio():
    return patch(
        "app.services.transcription_engine.librosa.load",
        return_value=(np.zeros(32000, dtype=np.float32), 16000),
    )


# --------------------------------------------------------------------------
# Detector
# --------------------------------------------------------------------------

def test_detector_matches_torch_oom_class_name():
    class OutOfMemoryError(RuntimeError):
        pass

    assert is_cuda_oom_error(OutOfMemoryError("CUDA out of memory")) is True


def test_detector_matches_async_kernel_error_message():
    """The real-world symptom: a plain RuntimeError with 'out of memory'."""
    assert is_cuda_oom_error(RuntimeError(OOM_MESSAGE)) is True


def test_detector_ignores_unrelated_errors():
    assert is_cuda_oom_error(ValueError("bad audio header")) is False


# --------------------------------------------------------------------------
# output_scores must be preserved: dropping it silently zeroes confidence
# (transformers nulls sequences_scores when output_scores=False)
# --------------------------------------------------------------------------

def test_beam_search_keeps_output_scores():
    engine = _make_engine(beam_size=5)
    seen = {}

    def _capture(*args, **kwargs):
        seen.update(kwargs)
        return _ok_generate_result()

    engine.model.generate.side_effect = _capture

    with _patch_audio():
        engine.transcribe(MagicMock(name="a.mp3"))

    assert seen["num_beams"] == 5
    assert seen.get("output_scores") is True, (
        "beam search confidence comes from sequences_scores, which transformers "
        "sets to None unless output_scores=True"
    )


def test_greedy_keeps_output_scores_for_transition_scores():
    engine = _make_engine(beam_size=1)
    seen = {}

    def _capture(*args, **kwargs):
        seen.update(kwargs)
        return _ok_generate_result()

    engine.model.generate.side_effect = _capture

    with _patch_audio():
        engine.transcribe(MagicMock(name="a.mp3"))

    assert seen["num_beams"] == 1
    assert seen.get("output_scores") is True, (
        "greedy decoding needs per-step scores for compute_transition_scores"
    )


# --------------------------------------------------------------------------
# Recovery behaviour
# --------------------------------------------------------------------------

def test_transient_oom_retries_greedy_and_succeeds():
    """First attempt OOMs; the engine must retry degraded and still transcribe."""
    engine = _make_engine(beam_size=5)
    engine.model.generate.side_effect = [
        RuntimeError(OOM_MESSAGE),
        _ok_generate_result(),
    ]

    with _patch_audio():
        result = engine.transcribe(MagicMock(name="a.mp3"))

    assert result is not None
    assert result["transcript"] == "hello"
    assert engine.model.generate.call_count == 2

    first = engine.model.generate.call_args_list[0].kwargs
    second = engine.model.generate.call_args_list[1].kwargs
    assert first["num_beams"] == 5
    assert second["num_beams"] == 1, "retry must shrink the memory footprint"


def test_oom_releases_cuda_cache():
    engine = _make_engine(beam_size=5)
    engine.model.generate.side_effect = [
        RuntimeError(OOM_MESSAGE),
        _ok_generate_result(),
    ]

    with _patch_audio(), patch(
        "app.services.transcription_engine.torch.cuda.empty_cache"
    ) as empty_cache:
        engine.transcribe(MagicMock(name="a.mp3"))

    assert empty_cache.called, "allocator must be reclaimed when an OOM is seen"


def test_allocator_reclaimed_before_every_file():
    """Proactive reclaim: the async OOM from the previous file is cleaned up."""
    engine = _make_engine(beam_size=5)
    engine.model.generate.return_value = _ok_generate_result()

    with _patch_audio(), patch(
        "app.services.transcription_engine.torch.cuda.empty_cache"
    ) as empty_cache:
        engine.transcribe(MagicMock(name="a.mp3"))

    assert empty_cache.called, (
        "a late-reported OOM leaves the allocator full; reclaim before each file"
    )


def test_persistent_oom_returns_none_and_never_raises():
    """Exhausted retries must not propagate — an escaping OOM wedges the loop."""
    engine = _make_engine(beam_size=5)
    engine.model.generate.side_effect = RuntimeError(OOM_MESSAGE)

    with _patch_audio(), patch(
        "app.services.transcription_engine.torch.cuda.empty_cache"
    ):
        result = engine.transcribe(MagicMock(name="a.mp3"))

    assert result is None
    assert engine.model.generate.call_count == 2, "one degraded retry, then give up"


def test_non_oom_errors_still_propagate_internally():
    """Only OOM is retried; genuine failures must not be masked by the retry."""
    engine = _make_engine(beam_size=5)
    engine.model.generate.side_effect = ValueError("tokenizer exploded")

    with _patch_audio(), patch(
        "app.services.transcription_engine.torch.cuda.empty_cache"
    ):
        result = engine.transcribe(MagicMock(name="a.mp3"))

    assert result is None
    assert engine.model.generate.call_count == 1, "do not retry non-OOM failures"


def test_transcription_oom_error_is_runtimeerror_subclass():
    assert issubclass(TranscriptionOutOfMemoryError, RuntimeError)


# --------------------------------------------------------------------------
# Queue processor: the site where the async OOM actually surfaces
# --------------------------------------------------------------------------

def test_queue_processor_reclaims_gpu_memory_after_failure(tmp_path):
    from app.services import queue_processor as qp

    processor = qp.QueueProcessor()
    audio_file = tmp_path / "10-30-26 5-55-15 PM_Mutual Aid Networks_Statewide EMS.mp3"
    audio_file.write_bytes(b"not-really-audio")

    processor.engine = MagicMock()
    processor.engine.transcribe = MagicMock(side_effect=RuntimeError(OOM_MESSAGE))

    asyncio.run(processor._process_file(audio_file))

    assert processor.engine.release_gpu_memory.called, (
        "a failure at the await point must still reclaim GPU memory"
    )


# --------------------------------------------------------------------------
# NER must not seize the GPU when the operator configured CPU — otherwise
# setting model.device: cpu does not actually relieve VRAM pressure
# --------------------------------------------------------------------------

def test_ner_uses_cpu_when_configured_cpu(monkeypatch):
    from app.services import ner_service
    from app.config import get_settings

    monkeypatch.setattr(get_settings().config.model, "device", "cpu")
    monkeypatch.setattr(
        ner_service, "_resolve_ner_target", lambda path: "org/incident_ner_v1"
    )

    with patch("app.services.ner_service.pipeline") as pipe, patch(
        "app.services.ner_service.torch.backends.mps.is_available", return_value=False
    ):
        assert ner_service.load_ner_model("ignored") is True

    assert pipe.call_args.kwargs["device"] == -1, "NER must stay off the GPU"


def test_ner_uses_gpu_when_configured_cuda(monkeypatch):
    from app.services import ner_service
    from app.config import get_settings

    monkeypatch.setattr(get_settings().config.model, "device", "cuda")
    monkeypatch.setattr(
        ner_service, "_resolve_ner_target", lambda path: "org/incident_ner_v1"
    )

    with patch("app.services.ner_service.pipeline") as pipe, patch(
        "app.services.ner_service.torch.cuda.is_available", return_value=True
    ):
        assert ner_service.load_ner_model("ignored") is True

    assert pipe.call_args.kwargs["device"] == 0
