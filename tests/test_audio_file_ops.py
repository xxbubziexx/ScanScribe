"""Unit tests for defensive audio file operations (safe_unlink / safe_async_unlink)."""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from app.utils.audio_file_ops import safe_unlink, safe_async_unlink


def test_safe_unlink_existing_file():
    """Verify that safe_unlink deletes an existing file cleanly."""
    with tempfile.NamedTemporaryFile(delete=False) as tf:
        tf.write(b"test data")
        temp_path = tf.name

    assert os.path.exists(temp_path)
    success = safe_unlink(temp_path)
    assert success is True
    assert not os.path.exists(temp_path)


def test_safe_unlink_nonexistent_file():
    """Verify that safe_unlink returns True for an already deleted / missing file."""
    fake_path = Path("non_existent_audio_file_12345.wav")
    assert not fake_path.exists()
    assert safe_unlink(fake_path) is True


def test_safe_unlink_retry_success():
    """Verify that safe_unlink retries when encountering transient PermissionError."""
    test_path = Path("simulated_locked_file.wav")
    
    with patch.object(Path, "exists", return_value=True):
        # Fail once with PermissionError, succeed on second attempt
        mock_unlink = MagicMock(side_effect=[PermissionError("File locked by indexer"), None])
        with patch.object(Path, "unlink", mock_unlink):
            with patch("time.sleep") as mock_sleep:
                success = safe_unlink(test_path, retries=2, delay=0.01)
                assert success is True
                assert mock_unlink.call_count == 2
                assert mock_sleep.call_count == 1


@pytest.mark.asyncio
async def test_safe_async_unlink_existing_file():
    """Verify that safe_async_unlink deletes an existing file cleanly."""
    with tempfile.NamedTemporaryFile(delete=False) as tf:
        tf.write(b"test data async")
        temp_path = tf.name

    assert os.path.exists(temp_path)
    success = await safe_async_unlink(temp_path)
    assert success is True
    assert not os.path.exists(temp_path)


@pytest.mark.asyncio
async def test_safe_async_unlink_retry_success():
    """Verify that safe_async_unlink retries when encountering transient PermissionError."""
    test_path = Path("simulated_locked_file_async.wav")
    
    with patch.object(Path, "exists", return_value=True):
        mock_unlink = MagicMock(side_effect=[PermissionError("File locked"), None])
        with patch.object(Path, "unlink", mock_unlink):
            with patch("asyncio.sleep") as mock_sleep:
                success = await safe_async_unlink(test_path, retries=2, delay=0.01)
                assert success is True
                assert mock_unlink.call_count == 2
                assert mock_sleep.call_count == 1
