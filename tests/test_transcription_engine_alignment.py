from unittest.mock import MagicMock, patch
import pytest
from app.services.transcription_engine import TranscriptionEngine


def test_vocab_alignment_english_model():
    engine = TranscriptionEngine()
    engine.model_name = "sepiaapps/whisper-small.en-police-radio"

    mock_model = MagicMock()
    mock_model.config.vocab_size = 51864
    mock_model.config.is_multilingual = False

    mock_proc_bad = MagicMock()
    mock_proc_bad.tokenizer = [0] * 51865  # Multilingual mismatch

    mock_proc_good = MagicMock()
    mock_proc_good.tokenizer = [0] * 51864  # Aligned English

    with patch("app.services.transcription_engine.WhisperForConditionalGeneration.from_pretrained", return_value=mock_model), \
         patch("app.services.transcription_engine.WhisperProcessor.from_pretrained", side_effect=[mock_proc_bad, mock_proc_good]):
        success = engine.load_model()
        assert success is True
        assert engine.is_english_only is True
        assert len(engine.processor.tokenizer) == 51864


def test_vocab_alignment_multilingual_model():
    engine = TranscriptionEngine()
    engine.model_name = "openai/whisper-small"

    mock_model = MagicMock()
    mock_model.config.vocab_size = 51865
    mock_model.config.is_multilingual = True

    mock_proc = MagicMock()
    mock_proc.tokenizer = [0] * 51865

    with patch("app.services.transcription_engine.WhisperForConditionalGeneration.from_pretrained", return_value=mock_model), \
         patch("app.services.transcription_engine.WhisperProcessor.from_pretrained", return_value=mock_proc):
        success = engine.load_model()
        assert success is True
        assert engine.is_english_only is False
        assert len(engine.processor.tokenizer) == 51865


def test_component_wise_processor_fallback():
    engine = TranscriptionEngine()
    engine.model_name = "sepiaapps/whisper-small.en-police-radio"

    mock_model = MagicMock()
    mock_model.config.vocab_size = 51864
    mock_model.config.is_multilingual = False

    mock_fe = MagicMock()
    mock_tok = MagicMock()
    mock_tok.__len__.return_value = 51864

    mock_proc = MagicMock()
    mock_proc.tokenizer = [0] * 51864

    mock_processor_cls = MagicMock(return_value=mock_proc)
    mock_processor_cls.from_pretrained.side_effect = TypeError("got multiple values for argument 'feature_extractor'")

    # WhisperProcessor.from_pretrained throws duplicate argument error
    with patch("app.services.transcription_engine.WhisperForConditionalGeneration.from_pretrained", return_value=mock_model), \
         patch("app.services.transcription_engine.WhisperProcessor", mock_processor_cls), \
         patch("transformers.AutoFeatureExtractor.from_pretrained", return_value=mock_fe), \
         patch("transformers.WhisperTokenizer.from_pretrained", return_value=mock_tok):
        success = engine.load_model()
        assert success is True
        assert engine.is_english_only is True
        assert len(engine.processor.tokenizer) == 51864
