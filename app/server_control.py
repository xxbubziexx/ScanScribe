"""ScanScribe server lifecycle commands (start/stop/restart/status/logs/open).

Used by app.cli; split out so the maintenance CLI stays small.
"""
import argparse
import os
import sys
import time
import subprocess
import signal
from pathlib import Path
import urllib.request
import urllib.error
import json
import webbrowser

BASE_DIR = Path(__file__).resolve().parent.parent
PID_FILE = BASE_DIR / ".scanscribe.pid"
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "scanscribe.log"
DEFAULT_PORT = 8000
DEFAULT_HOST = "0.0.0.0"


def _is_pid_running(pid: int) -> bool:
    """Check if process with PID is running."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            SYNCHRONIZE = 0x00100000
            process = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
            if process != 0:
                kernel32.CloseHandle(process)
                return True
            return False
        except Exception:
            # Fallback using tasklist
            try:
                out = subprocess.check_output(
                    ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                    stderr=subprocess.DEVNULL,
                    text=True
                )
                return str(pid) in out
            except Exception:
                return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


def _get_stored_pid() -> tuple[int | None, int]:
    """Return (pid, port) from PID file if valid."""
    if not PID_FILE.is_file():
        return None, DEFAULT_PORT
    try:
        content = PID_FILE.read_text().strip().split(":")
        pid = int(content[0])
        port = int(content[1]) if len(content) > 1 else DEFAULT_PORT
        if _is_pid_running(pid):
            return pid, port
        # Stale PID file
        try:
            PID_FILE.unlink(missing_ok=True)
        except Exception:
            pass
        return None, port
    except Exception:
        return None, DEFAULT_PORT


def _save_pid(pid: int, port: int):
    """Write PID and port to file."""
    try:
        PID_FILE.write_text(f"{pid}:{port}")
    except Exception as e:
        print(f"Warning: Could not write PID file: {e}", file=sys.stderr)


def _remove_pid():
    """Remove PID file."""
    try:
        PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def _check_health(port: int, timeout: float = 1.0) -> bool:
    """Check if server is responding on /health."""
    url = f"http://127.0.0.1:{port}/health"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ScanScribe-CLI"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def cmd_start(args):
    """Start ScanScribe server."""
    port = args.port or DEFAULT_PORT
    host = args.host or DEFAULT_HOST
    silent = getattr(args, "silent", False)
    foreground = getattr(args, "foreground", False)

    existing_pid, existing_port = _get_stored_pid()
    if existing_pid:
        if not silent:
            print(f"[!] ScanScribe is already running (PID: {existing_pid}) at http://localhost:{existing_port}")
        return 0

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    if foreground:
        if not silent:
            print(f"[*] Starting ScanScribe in foreground on http://localhost:{port}...")
        import uvicorn
        os.chdir(str(BASE_DIR))
        uvicorn.run("app.main:app", host=host, port=port, log_level="info")
        return 0

    # Background / Daemon spawn
    cmd = [
        sys.executable,
        "-m", "uvicorn",
        "app.main:app",
        "--host", host,
        "--port", str(port),
    ]

    log_fh = open(LOG_FILE, "a", encoding="utf-8", buffering=1)

    if not silent:
        print(f"[*] Spawning ScanScribe in background on port {port}...")

    os.chdir(str(BASE_DIR))

    if sys.platform == "win32":
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        proc = subprocess.Popen(
            cmd,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=flags,
            cwd=str(BASE_DIR),
            close_fds=True,
        )
    else:
        proc = subprocess.Popen(
            cmd,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            cwd=str(BASE_DIR),
            close_fds=True,
        )

    _save_pid(proc.pid, port)

    # Wait for server to become healthy
    started = False
    for _ in range(25):
        time.sleep(0.4)
        if _check_health(port, timeout=0.5):
            started = True
            break
        if proc.poll() is not None:
            break

    if not started and proc.poll() is not None:
        print(f"[X] ScanScribe failed to start (exit code {proc.returncode}). Check logs at: {LOG_FILE}", file=sys.stderr)
        _remove_pid()
        return 1

    if not silent:
        print("\n========================================================")
        print("  ScanScribe is running in the background!")
        print(f"  PID:    {proc.pid}")
        print(f"  Web UI: http://localhost:{port}")
        print(f"  Logs:   {LOG_FILE}")
        print("========================================================")
        print("  Useful CLI commands:")
        print("    scanscribe logs     - View live transcription logs")
        print("    scanscribe status   - Check health & system stats")
        print("    scanscribe stop     - Gracefully stop ScanScribe")
        print("========================================================\n")
        try:
            webbrowser.open(f"http://localhost:{port}")
        except Exception:
            pass

    return 0


def cmd_stop(args):
    """Stop ScanScribe server."""
    pid, port = _get_stored_pid()
    if not pid:
        print("[!] ScanScribe does not appear to be running.")
        _remove_pid()
        return 0

    print(f"[*] Stopping ScanScribe (PID: {pid})...")

    if sys.platform == "win32":
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            print(f"Error stopping process: {e}", file=sys.stderr)
    else:
        try:
            os.kill(pid, signal.SIGTERM)
            for _ in range(15):
                time.sleep(0.3)
                if not _is_pid_running(pid):
                    break
            if _is_pid_running(pid):
                os.kill(pid, signal.SIGKILL)
        except Exception as e:
            print(f"Error stopping process: {e}", file=sys.stderr)

    _remove_pid()
    print("[✓] ScanScribe stopped.")
    return 0


def cmd_restart(args):
    """Restart ScanScribe server."""
    cmd_stop(args)
    time.sleep(1)
    return cmd_start(args)


def cmd_status(args):
    """Check ScanScribe status."""
    pid, port = _get_stored_pid()
    if not pid:
        print("[X] ScanScribe is NOT running.")
        return 1

    is_healthy = _check_health(port)
    health_str = "Healthy (HTTP 200)" if is_healthy else "Starting / Unresponsive"

    print("\n--------------------------------------------------------")
    print(f"  ScanScribe Status: RUNNING")
    print(f"  PID:        {pid}")
    print(f"  URL:        http://localhost:{port}")
    print(f"  Health:     {health_str}")
    print(f"  Log File:   {LOG_FILE}")
    print("--------------------------------------------------------\n")
    return 0


def cmd_logs(args):
    """View / tail ScanScribe log file."""
    if not LOG_FILE.is_file():
        print(f"[!] No log file found at {LOG_FILE}. Has ScanScribe been started?")
        return 1

    num_lines = args.lines or 50
    follow = not args.no_follow

    print(f"[*] Reading logs from {LOG_FILE} (Ctrl+C to exit)...")
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            for line in lines[-num_lines:]:
                print(line, end="")

            if not follow:
                return 0

            # Follow mode
            f.seek(0, os.SEEK_END)
            while True:
                line = f.readline()
                if line:
                    print(line, end="", flush=True)
                else:
                    time.sleep(0.2)
    except KeyboardInterrupt:
        print("\n[*] Exited log viewer.")
    return 0


def cmd_open(args):
    """Open ScanScribe in default browser."""
    _, port = _get_stored_pid()
    url = f"http://localhost:{port}"
    print(f"[*] Opening {url} in your browser...")
    webbrowser.open(url)
    return 0


