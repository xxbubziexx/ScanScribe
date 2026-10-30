from unittest.mock import MagicMock, patch
import pytest
from app import server_control as sc


def test_check_for_updates_detects_difference():
    with patch("subprocess.check_output") as mock_check:
        mock_check.side_effect = [
            "abc1234\n",  # local_sha
            "def5678\trefs/heads/main\n",  # ls-remote
        ]
        info = sc.check_for_updates(target_branch="main", timeout=1.0)
        assert info is not None
        assert info["local_sha"] == "abc1234"
        assert info["remote_sha"] == "def5678"
        assert info["branch"] == "main"


def test_check_for_updates_none_when_equal():
    with patch("subprocess.check_output") as mock_check:
        mock_check.side_effect = [
            "abc1234\n",  # local_sha
            "abc1234\trefs/heads/main\n",  # ls-remote
        ]
        info = sc.check_for_updates(target_branch="main", timeout=1.0)
        assert info is None


def test_check_for_updates_exception_returns_none():
    with patch("subprocess.check_output", side_effect=Exception("network down")):
        info = sc.check_for_updates(target_branch="main", timeout=1.0)
        assert info is None


def test_print_update_banner(capsys):
    sc.print_update_banner(None)
    captured = capsys.readouterr()
    assert captured.out == ""

    sc.print_update_banner({"local_sha": "abc1234", "remote_sha": "def5678", "branch": "main"})
    captured = capsys.readouterr()
    assert "New ScanScribe update available on 'main'!" in captured.out
    assert "abc1234" in captured.out
    assert "def5678" in captured.out
    assert "scanscribe update" in captured.out


def test_cmd_update_already_up_to_date(capsys):
    args = MagicMock()
    args.branch = "main"
    args.force = False
    args.yes = True
    args.restart = False

    with patch("subprocess.run") as mock_run, \
         patch("subprocess.check_output") as mock_out, \
         patch.object(sc, "_get_stored_pid", return_value=(None, 8000)), \
         patch.object(sc, "_find_pid_listening_on_port", return_value=None), \
         patch.object(sc, "_check_health", return_value=False), \
         patch.object(sc, "_is_pid_running", return_value=False):
        mock_out.side_effect = ["abc1234\n", "abc1234\n"]
        rc = sc.cmd_update(args)
        assert rc == 0
        captured = capsys.readouterr()
        assert "already up to date" in captured.out


def test_cmd_update_aborts_when_instance_running(capsys):
    args = MagicMock()
    args.branch = "main"
    args.port = 8000
    args.force = False
    args.yes = True
    args.restart = False

    with patch("subprocess.run") as mock_run, \
         patch.object(sc, "_get_stored_pid", return_value=(9999, 8000)), \
         patch.object(sc, "_is_pid_running", return_value=True):
        rc = sc.cmd_update(args)
        assert rc == 1
        captured = capsys.readouterr()
        assert "Error: ScanScribe is currently running on port 8000 (PID: 9999)" in captured.out
        assert "The instance must be stopped before executing the update" in captured.out
        assert "scanscribe stop" in captured.out
        # Subprocess (git fetch/pull) must NOT be called
        mock_run.assert_not_called()


def test_cmd_update_aborts_when_port_listener_running(capsys):
    args = MagicMock()
    args.branch = "main"
    args.port = 8000
    args.force = False
    args.yes = True
    args.restart = False

    with patch("subprocess.run") as mock_run, \
         patch.object(sc, "_get_stored_pid", return_value=(None, 8000)), \
         patch.object(sc, "_find_pid_listening_on_port", return_value=8888), \
         patch.object(sc, "_is_pid_running", return_value=True):
        rc = sc.cmd_update(args)
        assert rc == 1
        captured = capsys.readouterr()
        assert "Error: ScanScribe is currently running on port 8000 (PID: 8888)" in captured.out
        assert "scanscribe stop" in captured.out
        mock_run.assert_not_called()


def test_cmd_update_aborts_when_health_check_responds(capsys):
    args = MagicMock()
    args.branch = "main"
    args.port = 8000
    args.force = False
    args.yes = True
    args.restart = False

    with patch("subprocess.run") as mock_run, \
         patch.object(sc, "_get_stored_pid", return_value=(None, 8000)), \
         patch.object(sc, "_find_pid_listening_on_port", return_value=None), \
         patch.object(sc, "_check_health", return_value=True):
        rc = sc.cmd_update(args)
        assert rc == 1
        captured = capsys.readouterr()
        assert "Error: ScanScribe is currently running on port 8000" in captured.out
        assert "scanscribe stop" in captured.out
        mock_run.assert_not_called()


def test_cmd_update_restarts_when_requested():
    args = MagicMock()
    args.branch = "main"
    args.port = 8000
    args.force = False
    args.yes = True
    args.restart = True

    with patch("subprocess.run"), \
         patch("subprocess.check_output", return_value="abc1234\n"), \
         patch.object(sc, "_get_stored_pid", return_value=(None, 8000)), \
         patch.object(sc, "_find_pid_listening_on_port", return_value=None), \
         patch.object(sc, "_check_health", return_value=False), \
         patch.object(sc, "_is_pid_running", return_value=False), \
         patch.object(sc, "cmd_start", return_value=0) as mock_start:
        rc = sc.cmd_update(args)
        assert rc == 0
        mock_start.assert_called_once_with(args)
