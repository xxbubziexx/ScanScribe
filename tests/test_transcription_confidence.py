"""Unit tests for Whisper ASR token-level log-prob confidence extraction."""
import sys
from unittest.mock import MagicMock
import numpy as np
import pytest

from app.services.transcription_engine import TranscriptionEngine


def _is_mock_torch(mod):
    return isinstance(mod, MagicMock) or hasattr(mod, "_mock_return_value")


def test_confidence_greedy_decoding_derived_from_logits():
    """Verify that greedy decoding (no sequences_scores) derives confidence via transition scores."""
    import torch

    engine = TranscriptionEngine()
    engine.device = "cpu"
    engine.processor = MagicMock()
    engine.model = MagicMock()

    mock_input_features = MagicMock()
    mock_input_features.to.return_value = mock_input_features
    engine.processor.return_value.input_features = mock_input_features
    engine.processor.batch_decode.return_value = ["Engine 4 on scene at Main and 4th"]

    mock_generated_ids = MagicMock(spec=["sequences", "scores"])

    if _is_mock_torch(torch):
        engine.model.dtype = "float32"
        mock_generated_ids.sequences = [[50258, 50259, 50359, 3124, 604, 50257]]
        mock_generated_ids.scores = [MagicMock() for _ in range(5)]

        fake_trans_scores = MagicMock()
        fake_trans_scores.numel.return_value = 5
        fake_log_probs = MagicMock()
        fake_trans_scores.__getitem__.return_value = fake_log_probs
        fake_log_probs.__getitem__.return_value = fake_log_probs
        fake_log_probs.__len__.return_value = 5

        torch.isfinite.return_value = True
        torch.exp.return_value = MagicMock(item=MagicMock(return_value=0.92))
        torch.clamp.side_effect = lambda x, min_val, max_val: x

        engine.model.compute_transition_scores.return_value = fake_trans_scores
        engine.model.generate.return_value = mock_generated_ids

        fake_audio = np.zeros(16000, dtype=np.float32)
        transcript, confidence = engine._transcribe_chunk(fake_audio)

        assert transcript == "Engine 4 on scene at Main and 4th"
        assert engine.model.compute_transition_scores.called
        assert confidence == 0.92
        assert confidence != 0.85
    else:
        engine.model.dtype = torch.float32
        mock_generated_ids.sequences = torch.tensor([[50258, 50259, 50359, 3124, 604, 50257]])
        mock_generated_ids.scores = [torch.randn(1, 51864) for _ in range(5)]

        fake_log_probs = torch.tensor([[-0.08, -0.09, -0.07, -0.10, -0.08]])
        engine.model.compute_transition_scores.return_value = fake_log_probs
        engine.model.generate.return_value = mock_generated_ids

        fake_audio = np.zeros(16000, dtype=np.float32)
        transcript, confidence = engine._transcribe_chunk(fake_audio)

        assert transcript == "Engine 4 on scene at Main and 4th"
        assert engine.model.compute_transition_scores.called
        assert 0.0 <= confidence <= 1.0
        assert confidence != 0.85
        expected_prob = float(torch.clamp(torch.exp(fake_log_probs.mean()), 0.0, 1.0).item())
        assert abs(confidence - expected_prob) < 1e-4


def test_confidence_beam_search_derived_from_sequences_scores():
    """Verify that beam search with sequences_scores computes confidence and clamps correctly."""
    import torch

    engine = TranscriptionEngine()
    engine.device = "cpu"
    engine.processor = MagicMock()
    engine.model = MagicMock()

    mock_input_features = MagicMock()
    mock_input_features.to.return_value = mock_input_features
    engine.processor.return_value.input_features = mock_input_features
    engine.processor.batch_decode.return_value = ["Medic 12 transport en route"]

    mock_generated_ids = MagicMock()

    if _is_mock_torch(torch):
        engine.model.dtype = "float32"
        mock_generated_ids.sequences_scores = [-0.15, -0.45, -0.80]
        torch.isfinite.return_value = True
        torch.exp.return_value = MagicMock(item=MagicMock(return_value=0.8607))
        torch.clamp.side_effect = lambda x, min_val, max_val: x

        engine.model.generate.return_value = mock_generated_ids

        fake_audio = np.zeros(16000, dtype=np.float32)
        transcript, confidence = engine._transcribe_chunk(fake_audio)

        assert transcript == "Medic 12 transport en route"
        assert confidence == 0.8607
    else:
        engine.model.dtype = torch.float32
        mock_generated_ids.sequences_scores = torch.tensor([-0.15, -0.45, -0.80])
        mock_generated_ids.sequences = torch.tensor([[1, 2, 3]])
        engine.model.generate.return_value = mock_generated_ids

        fake_audio = np.zeros(16000, dtype=np.float32)
        transcript, confidence = engine._transcribe_chunk(fake_audio)

        assert transcript == "Medic 12 transport en route"
        assert 0.0 <= confidence <= 1.0
        expected_prob = float(torch.clamp(torch.exp(torch.tensor(-0.15)), 0.0, 1.0).item())
        assert abs(confidence - expected_prob) < 1e-4


def test_confidence_fallback_on_computation_error():
    """Verify graceful zero-confidence assignment if transition scores computation fails."""
    import torch

    engine = TranscriptionEngine()
    engine.device = "cpu"
    engine.processor = MagicMock()
    engine.model = MagicMock()

    mock_input_features = MagicMock()
    mock_input_features.to.return_value = mock_input_features
    engine.processor.return_value.input_features = mock_input_features
    engine.processor.batch_decode.return_value = ["Radio noise"]

    mock_generated_ids = MagicMock(spec=["sequences", "scores"])
    if _is_mock_torch(torch):
        engine.model.dtype = "float32"
        mock_generated_ids.sequences = [[1, 2]]
        mock_generated_ids.scores = [MagicMock()]
    else:
        engine.model.dtype = torch.float32
        mock_generated_ids.sequences = torch.tensor([[1, 2]])
        mock_generated_ids.scores = [torch.randn(1, 10)]

    # Simulate unexpected runtime error in compute_transition_scores
    engine.model.compute_transition_scores.side_effect = RuntimeError("CUDA tensor dimension mismatch")
    engine.model.generate.return_value = mock_generated_ids

    fake_audio = np.zeros(16000, dtype=np.float32)
    transcript, confidence = engine._transcribe_chunk(fake_audio)

    assert transcript == "Radio noise"
    # Should safely return 0.0, never crash and never return legacy 0.85
    assert confidence == 0.0
