"""Whisper transcription engine with CPU/GPU optimization."""
import logging
import tempfile
import time
import os
import torch
from pathlib import Path
from typing import Optional, Dict, Any
from transformers import WhisperProcessor, WhisperForConditionalGeneration
import librosa
import numpy as np
import soundfile as sf

from ..config import get_settings

try:
    from silero_vad import load_silero_vad, get_speech_timestamps
    _SILERO_AVAILABLE = True
except ImportError:
    _SILERO_AVAILABLE = False

logger = logging.getLogger(__name__)

# Get CPU count for optimization
CPU_COUNT = os.cpu_count() or 4

# Transcript value when VAD detects no speech (audio kept, Whisper skipped)
VAD_REJECTED_TRANSCRIPT = "VAD_REJECTED"


class TranscriptionEngine:
    """Whisper transcription engine optimized for CPU/GPU."""
    
    def __init__(self):
        """Initialize the transcription engine."""
        settings = get_settings()
        self.config = settings.config
        self.model = None
        self.processor = None
        self.device = None
        self.model_name = self.config.model.name
        self.model_path = Path(self.config.model.path) / self.model_name
        self._vad_model = None  # Lazy-loaded Silero VAD
        
    def load_model(self):
        """Load Whisper model at startup (CPU or GPU)."""
        start_time = time.time()
        
        # Determine device
        device_config = self.config.model.device.lower()
        
        if device_config == "cuda":
            if torch.cuda.is_available():
                self.device = "cuda"
                gpu_name = torch.cuda.get_device_name(0)
                logger.info(f"🎮 GPU detected: {gpu_name}")
            else:
                logger.warning("⚠️ CUDA requested but not available, falling back to CPU")
                self.device = "cpu"
        else:
            self.device = "cpu"
            logger.info("💻 Using CPU for transcription")
        
        # Set PyTorch optimization flags for CPU
        if self.device == "cpu":
            # Use all available CPU cores unless config specifies fewer
            num_threads = self.config.model.workers
            if num_threads <= 0 or num_threads > CPU_COUNT:
                num_threads = CPU_COUNT
            
            # Intra-op parallelism (within operations)
            torch.set_num_threads(num_threads)
            # Inter-op parallelism (between operations)
            torch.set_num_interop_threads(max(1, num_threads // 2))
            # Optimize denormal numbers
            torch.set_flush_denormal(True)
            
            # Set environment variables for additional optimization
            os.environ.setdefault('OMP_NUM_THREADS', str(num_threads))
            os.environ.setdefault('MKL_NUM_THREADS', str(num_threads))
            
            logger.info(f"⚙️ CPU optimization: {num_threads} threads (of {CPU_COUNT} available)")
        
        # Load model and processor
        logger.info(f"📦 Loading model: {self.model_name}")
        
        try:
            self.processor = WhisperProcessor.from_pretrained(str(self.model_path))
            self.model = WhisperForConditionalGeneration.from_pretrained(
                str(self.model_path),
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                low_cpu_mem_usage=True
            )
            
            # Move model to device
            self.model.to(self.device)
            
            # Optimize for inference
            self.model.eval()
            
            # Enable inference mode optimizations
            if self.device == "cpu":
                # CPU optimizations
                torch.backends.cudnn.enabled = False
            else:
                # GPU optimizations
                torch.backends.cudnn.benchmark = True
                self.model.half()  # FP16 for GPU
            
            load_time = time.time() - start_time
            logger.info(f"✅ Model loaded successfully in {load_time:.1f}s")
            logger.info(f"📊 Device: {self.device.upper()}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to load model: {e}")
            return False
    
    def transcribe(self, audio_path: Path) -> Optional[Dict[str, Any]]:
        """
        Transcribe audio file using Whisper with chunking for long audio.
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Dict with transcript, confidence, language, processing_time
        """
        if not self.model or not self.processor:
            logger.error("❌ Model not loaded")
            return None
        
        start_time = time.time()
        speech_only_audio_path = None  # Set when vad_save_speech_only and we wrote speech-only WAV
        
        # Whisper chunk settings from config
        CHUNK_LENGTH_S = self.config.advanced.chunk_length_s
        STRIDE_LENGTH_S = self.config.advanced.chunk_stride_s
        
        try:
            # Load audio with librosa (handles all formats)
            logger.info(f"🎵 Loading audio: {audio_path.name}")
            audio, sr = librosa.load(str(audio_path), sr=16000, mono=True)
            
            # Get audio duration
            duration = len(audio) / sr
            logger.info(f"⏱️ Duration: {duration:.2f}s")
            
            # VAD / silence trimming: gate (speech mode only) and optional chunking
            if self.config.transcription.vad_enabled:
                chunk_mode = getattr(
                    self.config.transcription, "vad_chunking_mode", "speech"
                ) or "speech"
                if self.config.transcription.vad_chunking_enabled and chunk_mode == "silence":
                    # VAD gate: skip Whisper if no speech detected
                    segments = self._get_speech_segments(audio, sr)
                    if segments is not None and len(segments) == 0:
                        processing_time = time.time() - start_time
                        logger.info(f"🔇 No speech detected (VAD), skipping Whisper — {VAD_REJECTED_TRANSCRIPT}")
                        return {
                            "transcript": VAD_REJECTED_TRANSCRIPT,
                            "language": "en",
                            "confidence": 0.0,
                            "duration": duration,
                            "processing_time": processing_time,
                        }
                    # Only cut out silence (keep everything above noise floor)
                    audio = self._get_silence_removed_audio(audio, sr)
                    logger.info(f"🔊 Silence removal: trimmed to {len(audio)/sr:.1f}s (above noise floor)")
                    if self.config.transcription.vad_save_speech_only:
                        fd, path = tempfile.mkstemp(suffix=".wav")
                        os.close(fd)
                        sf.write(path, audio, sr)
                        speech_only_audio_path = path
                        logger.info("💾 Wrote silence-trimmed WAV to temp for storage")
                else:
                    # Speech mode: VAD segments (or gate only)
                    segments = self._get_speech_segments(audio, sr)
                    if segments is not None and len(segments) == 0:
                        processing_time = time.time() - start_time
                        logger.info(f"🔇 No speech detected (VAD), skipping Whisper — {VAD_REJECTED_TRANSCRIPT}")
                        return {
                            "transcript": VAD_REJECTED_TRANSCRIPT,
                            "language": "en",
                            "confidence": 0.0,
                            "duration": duration,
                            "processing_time": processing_time,
                        }
                    if segments is not None and len(segments) > 0 and self.config.transcription.vad_chunking_enabled:
                        total_speech_s = sum(end - start for start, end in segments)
                        logger.info(f"🔊 VAD: {len(segments)} speech segment(s), {total_speech_s:.1f}s total — transcribing speech only")
                        pad = self.config.transcription.vad_segment_pad_s
                        parts = []
                        for start, end in segments:
                            s = max(0.0, start - pad)
                            e = min(duration, end + pad)
                            start_samp = int(s * sr)
                            end_samp = int(e * sr)
                            if end_samp > start_samp:
                                parts.append(audio[start_samp:end_samp])
                        if parts:
                            audio = np.concatenate(parts).astype(audio.dtype)
                            if self.config.transcription.vad_save_speech_only:
                                fd, path = tempfile.mkstemp(suffix=".wav")
                                os.close(fd)
                                sf.write(path, audio, sr)
                                speech_only_audio_path = path
                                logger.info("💾 Wrote speech-only WAV to temp for storage")
                    elif segments is not None and len(segments) > 0:
                        logger.info(f"🔊 VAD: {len(segments)} speech segment(s) — transcribing full file (chunking disabled)")
                # If segments is None (VAD error) in speech mode, fall through to full audio
            
            # Determine if chunking is needed (use current audio length, which may be VAD-trimmed)
            chunk_length_samples = CHUNK_LENGTH_S * sr
            stride_length_samples = STRIDE_LENGTH_S * sr
            audio_len = len(audio)
            
            # English-only transcription
            forced_decoder_ids = self.processor.get_decoder_prompt_ids(
                language="en",
                task="transcribe"
            )
            
            logger.info("🔄 Transcribing (en)...")
            
            with torch.inference_mode():
                if audio_len <= chunk_length_samples:
                    transcript, confidence = self._transcribe_chunk(
                        audio, forced_decoder_ids
                    )
                else:
                    num_chunks = int(np.ceil((audio_len - chunk_length_samples) / 
                                            (chunk_length_samples - stride_length_samples))) + 1
                    logger.info(f"📊 Processing {num_chunks} chunks...")
                    
                    transcripts = []
                    confidences = []
                    
                    for i in range(num_chunks):
                        start_sample = i * (chunk_length_samples - stride_length_samples)
                        end_sample = min(start_sample + chunk_length_samples, len(audio))
                        chunk = audio[start_sample:end_sample]
                        
                        if len(chunk) < sr:
                            continue
                        
                        chunk_text, chunk_conf = self._transcribe_chunk(
                            chunk, forced_decoder_ids
                        )
                        
                        if chunk_text:
                            transcripts.append(chunk_text)
                            confidences.append(chunk_conf)
                    
                    transcript = " ".join(transcripts)
                    confidence = sum(confidences) / len(confidences) if confidences else 0.0
            
            processing_time = time.time() - start_time
            
            logger.info(f"✅ Transcription complete in {processing_time:.2f}s")
            logger.info(f"📝 Text: {transcript[:100]}{'...' if len(transcript) > 100 else ''}")
            logger.info(f"📊 Confidence: {confidence:.2%}")
            
            out = {
                "transcript": transcript,
                "language": "en",
                "confidence": confidence,
                "duration": duration,
                "processing_time": processing_time
            }
            if speech_only_audio_path is not None:
                out["speech_only_audio_path"] = speech_only_audio_path
            return out
            
        except Exception as e:
            if speech_only_audio_path is not None and os.path.isfile(speech_only_audio_path):
                try:
                    os.unlink(speech_only_audio_path)
                except OSError:
                    pass
            logger.error(f"❌ Transcription failed: {e}")
            return None

    def _transcribe_chunk(self, audio_chunk: np.ndarray, forced_decoder_ids=None) -> tuple:
        """Transcribe a single audio chunk."""
        # Prepare inputs
        input_features = self.processor(
            audio_chunk,
            sampling_rate=16000,
            return_tensors="pt"
        ).input_features.to(device=self.device, dtype=self.model.dtype)        
        # Generate transcription
        generated_ids = self.model.generate(
            input_features,
            forced_decoder_ids=forced_decoder_ids,
            num_beams=self.config.transcription.beam_size,
            max_length=448,
            return_dict_in_generate=True,
            output_scores=True
        )
        
        # Decode
        transcript = self.processor.batch_decode(
            generated_ids.sequences,
            skip_special_tokens=True
        )[0].strip()
        
        # Confidence
        if hasattr(generated_ids, 'sequences_scores'):
            confidence = float(torch.exp(generated_ids.sequences_scores[0]))
        else:
            confidence = 0.85
        
        return transcript, confidence
    
    def _get_silence_removed_audio(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """
        Remove only long silence regions (below noise floor). Keeps everything above threshold.
        Returns concatenated audio with silence gaps replaced by short gaps.
        """
        threshold = self.config.transcription.silence_threshold
        min_silence_s = self.config.transcription.min_silence_duration_s
        gap_s = self.config.transcription.silence_gap_s
        frame_s = 0.05  # 50 ms frames
        frame_samples = int(sr * frame_s)
        n_frames = len(audio) // frame_samples
        if n_frames == 0:
            return audio
        # RMS per frame
        rms = np.array([
            np.sqrt(np.mean(audio[i * frame_samples:(i + 1) * frame_samples] ** 2))
            for i in range(n_frames)
        ])
        is_silence = rms < threshold
        # Find runs of silence (start_idx, end_idx) in frame indices
        silence_starts = np.where(np.diff(np.concatenate([[False], is_silence, [False]]).astype(int)) == 1)[0]
        silence_ends = np.where(np.diff(np.concatenate([[False], is_silence, [False]]).astype(int)) == -1)[0]
        gap_samples = int(sr * gap_s)
        parts = []
        prev_end_samp = 0
        for start_f, end_f in zip(silence_starts, silence_ends):
            dur_frames = end_f - start_f
            if dur_frames * frame_s < min_silence_s:
                continue  # keep short "silence" as content
            start_samp = start_f * frame_samples
            end_samp = min(end_f * frame_samples, len(audio))
            if start_samp > prev_end_samp:
                parts.append(audio[prev_end_samp:start_samp])
            parts.append(np.zeros(gap_samples, dtype=audio.dtype))
            prev_end_samp = end_samp
        if prev_end_samp < len(audio):
            parts.append(audio[prev_end_samp:])
        if not parts:
            return audio
        return np.concatenate(parts).astype(audio.dtype)

    def _get_speech_segments(self, audio: np.ndarray, sr: int) -> Optional[list]:
        """
        Run Silero VAD. Returns list of (start_sec, end_sec), or [] if no speech.
        Returns None if VAD unavailable or on error (caller falls back to full transcribe).
        """
        if not _SILERO_AVAILABLE:
            return None
        try:
            if self._vad_model is None:
                logger.info("🔊 Loading Silero VAD model (first use)...")
                self._vad_model, _ = torch.hub.load(
                    repo_or_dir="snakers4/silero-vad",
                    model="silero_vad",
                    force_reload=False,
                    trust_repo=True,
                )
                self._vad_model.eval()
            wav = torch.from_numpy(audio).float()
            threshold = self.config.transcription.vad_threshold
            speech_pad_ms = self.config.transcription.vad_speech_pad_ms
            min_speech_ms = self.config.transcription.vad_min_speech_duration_ms
            timestamps = get_speech_timestamps(
                wav,
                self._vad_model,
                threshold=threshold,
                sampling_rate=sr,
                return_seconds=True,
                speech_pad_ms=speech_pad_ms,
                min_speech_duration_ms=min_speech_ms,
            )
            if not timestamps:
                return []
            return [(t["start"], t["end"]) for t in timestamps]
        except Exception as e:
            logger.warning(f"VAD failed: {e}")
            return None

    def unload_model(self):
        """Unload model from memory."""
        if self.model:
            del self.model
            del self.processor
            self.model = None
            self.processor = None
        self._vad_model = None
        if self.device == "cuda":
            torch.cuda.empty_cache()
        logger.info("🗑️ Model unloaded from memory")


# Global engine instance
_engine = None


def get_engine() -> TranscriptionEngine:
    """Get or create transcription engine instance."""
    global _engine
    if _engine is None:
        _engine = TranscriptionEngine()
    return _engine
