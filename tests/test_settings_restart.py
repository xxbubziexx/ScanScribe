"""Tests for settings restart logic and SafeRotatingFileHandler."""
import asyncio
import os
import signal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from app.logging_config import SafeRotatingFileHandler
from app.routes.settings import _trigger_application_restart


def test_safe_rotating_file_handler_handles_permission_error(tmp_path):
    log_file = tmp_path / "test.log"
    log_file.write_text("initial log data\n")

    handler = SafeRotatingFileHandler(
        log_file,
        maxBytes=10,
        backupCount=2,
        encoding="utf-8",
    )

    with patch.object(handler, "rotate", side_effect=PermissionError(32, "The process cannot access the file")):
        # Rollover attempt should catch PermissionError gracefully without raising
        handler.doRollover()

    handler.close()


@pytest.mark.asyncio
async def test_trigger_application_restart_docker():
    with patch("pathlib.Path.exists", return_value=True), patch("os.kill") as mock_kill:
        _trigger_application_restart(delay_seconds=0.01)
        await asyncio.sleep(0.05)
        assert mock_kill.called
        assert mock_kill.call_args[0] == (os.getpid(), signal.SIGTERM)


@pytest.mark.asyncio
async def test_trigger_application_restart_native():
    with patch("pathlib.Path.exists", return_value=False), patch("subprocess.Popen") as mock_popen:
        _trigger_application_restart(delay_seconds=0.01)
        await asyncio.sleep(0.05)
        assert mock_popen.called
        cmd = mock_popen.call_args[0][0]
        assert "restart" in cmd

