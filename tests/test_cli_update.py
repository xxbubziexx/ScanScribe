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
         patch.object(sc, "_get_stored_pid", return_value=(None, None)), \
         patch.object(sc, "_is_pid_running", return_value=False):
        mock_out.side_effect = ["abc1234\n", "abc1234\n"]
        rc = sc.cmd_update(args)
        assert rc == 0
        captured = capsys.readouterr()
        assert "already up to date" in captured.out
