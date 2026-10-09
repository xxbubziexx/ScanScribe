# Phase 1: Repository Hygiene, Packaging & Setup Consolidation

> **Phase Order**: 1 of 5  
> **Status**: Ready for Implementation  
> **Estimated Execution Time**: ~1–2 hours  
> **Target Files**: Root directory, `docker/`, `scripts/`, `app/cli.py`, `pyproject.toml`

---

## 1. Objectives

1. Eliminate all zombie files and abandoned static assets from previous frontend iterations.
2. Resolve the split Docker configuration by centralizing Docker assets in [`docker/`](file:///a:/Scanscribe_Projects/scanscribe/docker).
3. Consolidate the sprawling collection of 6 setup/install scripts into a unified CLI tool in [`app/cli.py`](file:///a:/Scanscribe_Projects/scanscribe/app/cli.py) with standardized platform wrappers.
4. Establish a clean `pyproject.toml` specification for Python 3.10+ with pinned dependency groups.

---

## 2. Inventory of Dead Files to Remove

The following files exist in the project root solely as historical leftovers from the original Jinja2 / Alpine.js web dashboard:

| File / Directory | Size | Reason for Deletion |
| :--- | :--- | :--- |
| `dashboard.html` | ~21 KB | Legacy Jinja2 dashboard replaced by React SPA in `app/frontend/`. |
| `dashboard.css` | ~1.6 KB | Legacy stylesheet for deleted Alpine templates. |
| `chartjs.css` | ~726 B | Legacy Chart.js stylesheet; charts are now rendered via Recharts in React. |
| `bootstrap/` | ~Directory | Legacy CSS/JS libraries from 2024 initial prototype. |
| `assets/` | ~Directory | Legacy unbundled assets (icons, static images) superseded by `app/frontend/public/`. |
| `app/cli.py.local_backup` | ~Temporary | Local unmerged daemon script; logic will be merged into unified CLI. |

### Execution Command:
```powershell
Remove-Item -Force -Recurse "dashboard.html", "dashboard.css", "chartjs.css", "bootstrap", "assets", "app\cli.py.local_backup"
```

---

## 3. Docker Asset Consolidation

### Current Architecture Flaw:
The root directory currently contains:
* `Dockerfile.cpu`
* `Dockerfile.gpu`
* `docker-compose.cpu.example`
* `docker-compose.gpu.example`
* `requirements.cpu.example`
* `requirements.gpu.example`

Meanwhile, [`docker/`](file:///a:/Scanscribe_Projects/scanscribe/docker) contains only a `README.md`.

### Target Architecture:
All container build specifications and compose templates will reside within `docker/`. The root directory will maintain only `.dockerignore`.

```
docker/
├── Dockerfile.cpu
├── Dockerfile.gpu
├── docker-compose.cpu.example
├── docker-compose.gpu.example
├── requirements.cpu.example
├── requirements.gpu.example
└── README.md
```

### Action Steps:
1. Move container files into `docker/`:
   ```powershell
   Move-Item -Force "Dockerfile.cpu", "Dockerfile.gpu", "docker-compose.cpu.example", "docker-compose.gpu.example", "requirements.cpu.example", "requirements.gpu.example" "docker\"
   ```
2. Update `docker/docker-compose.*.example` build contexts so they correctly point to root:
   ```yaml
   services:
     scanscribe:
       build:
         context: ..
         dockerfile: docker/Dockerfile.cpu
   ```
3. Update [`README.md`](file:///a:/Scanscribe_Projects/scanscribe/README.md) instructions to reflect `docker compose -f docker/docker-compose.cpu.example up -d`.

---

## 4. Unification of Setup & Launcher Scripts

### Current Sprawl:
The repository currently contains **seven** distinct entrypoints with overlapping features:
* `setup.py` (Python installer script that duplicates pip/uv logic)
* `setup.ps1` & `setup.sh` (wrappers around `setup.py`)
* `install.ps1` & `install.sh` (curl-pipe-bash remote web installers)
* `start.bat` & `stop.bat` (Windows double-click wrappers)
* `app/cli.py` (Maintenance CLI for entity observation reindexing)

### The Unified Architecture:
ScanScribe will provide a single, robust Python CLI entrypoint via [`app/cli.py`](file:///a:/Scanscribe_Projects/scanscribe/app/cli.py), registered in `pyproject.toml` as `scanscribe`.

```
                       scanscribe [subcommand]
                                  │
       ┌───────────┬──────────────┼──────────────┬─────────────┐
       ▼           ▼              ▼              ▼             ▼
     start       stop          status          logs       rebuild-entities
  (Daemon/FG)  (Kill PID)   (Healthcheck)   (Live tail)   (Span reindex)
```

### Script Directory Organization:
```
scripts/
├── install.ps1      # Remote/local Windows installation & PATH setup
├── install.sh       # Remote/local Linux installation & systemd setup
├── start.bat        # Convenience wrapper: python -m app.cli start
└── stop.bat         # Convenience wrapper: python -m app.cli stop
```
Remove `setup.py`, `setup.ps1`, `setup.sh` from the repository root.

### Unified `app/cli.py` Specification:
The unified CLI merges the daemon lifecycle commands (`start`, `stop`, `restart`, `status`, `logs`, `open`) with maintenance commands (`rebuild-entities`, `db-migrate`):

```python
"""ScanScribe Unified CLI Entrypoint."""
import argparse
import sys

def main():
    parser = argparse.ArgumentParser(prog="scanscribe", description="ScanScribe Management CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Server daemon controls
    p_start = subparsers.add_parser("start", help="Start ScanScribe server")
    p_start.add_argument("--port", type=int, default=8000)
    p_start.add_argument("--host", default="0.0.0.0")
    p_start.add_argument("--foreground", action="store_true")
    
    subparsers.add_parser("stop", help="Stop ScanScribe server")
    subparsers.add_parser("status", help="Check server health and PID")
    subparsers.add_parser("logs", help="Stream live transcription logs")
    subparsers.add_parser("open", help="Open Web UI in browser")

    # Maintenance & Database tools
    p_rebuild = subparsers.add_parser("rebuild-entities", help="Reindex NER entities")
    p_rebuild.add_argument("--since", help="YYYY-MM-DD")
    p_rebuild.add_argument("--monitor", type=int)

    p_migrate = subparsers.add_parser("migrate", help="Run database migrations")

    args = parser.parse_args()
    # Route to handler...
```

---

## 5. Modern `pyproject.toml` Packaging

Create a clean, standardized [`pyproject.toml`](file:///a:/Scanscribe_Projects/scanscribe/pyproject.toml) at root to eliminate loose dependency management:

```toml
[build-system]
requires = ["setuptools>=68.0.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "scanscribe"
version = "2.1.0"
description = "AI-Powered Public Safety Radio Transcription & Incident Pipeline"
readme = "README.md"
requires-python = ">=3.10"
authors = [{ name = "ScanScribe Contributors" }]
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "sqlalchemy>=2.0.35",
    "alembic>=1.13.3",
    "pydantic>=2.9.2",
    "pyyaml>=6.0.2",
    "httpx>=0.27.2",
    "faster-whisper>=1.0.3",
    "torch>=2.2.0",
    "torchaudio>=2.2.0",
    "soundfile>=0.12.1",
    "transformers>=4.45.0",
    "slowapi>=0.1.9",
    "python-multipart>=0.0.12",
    "python-jose[cryptography]>=3.3.0",
    "passlib[bcrypt]>=1.7.4",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "ruff>=0.7.0",
    "mypy>=1.12.0",
]

[project.scripts]
scanscribe = "app.cli:main"
```

---

## 6. Verification Criteria

- [ ] Repository root has no `.html` or `.css` files.
- [ ] No `bootstrap/` or `assets/` folders at repository root.
- [ ] `docker/` contains all Dockerfiles and compose templates; `docker compose -f docker/docker-compose.cpu.example config` succeeds.
- [ ] Running `python -m app.cli --help` displays all commands (`start`, `stop`, `status`, `logs`, `rebuild-entities`).
- [ ] `git status` shows clean tracking with `.gitignore` properly excluding runtime files (`data/*.db-wal`, `data/*.db-shm`, `.venv/`).
