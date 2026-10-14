# ScanScribe Docker Deployment

While ScanScribe is optimized to run as a fast, native application with its own isolated virtual environment and CLI, Docker Compose files are actively maintained for homelab, TrueNAS SCALE, Unraid, and containerized edge environments.

---

## Key Features of ScanScribe Docker
- **Self-Migrating Startup:** `docker/entrypoint.sh` automatically runs `alembic upgrade head` on container boot. Updates are 100% hands-off.
- **Frontend Asset Resilience:** Pre-built React command center assets are preserved even when mounting `./app` from host.
- **PyTorch Memory Guarding:** Configured with `shm_size: 2gb` and graceful stop timeouts (`stop_grace_period: 30s`) to prevent PyTorch CUDA OOM or bus errors.
- **Unified Dependencies:** Builds directly from root `requirements.txt` with official PyTorch wheels (CPU or CUDA 12.4).

---

## Quick Start via Installer

You can deploy Docker automatically using the ScanScribe station installer:
- **Linux:** `curl -sSL https://raw.githubusercontent.com/xxbubziexx/ScanScribe/main/install.sh | bash -s -- --docker`
- **Windows:** `irm https://raw.githubusercontent.com/xxbubziexx/ScanScribe/main/install.ps1 | iex` *(Select Option 2: Docker)*

---

## Manual Deployment

### CPU Deployment

1. Copy the CPU compose template and initial configuration:
   ```bash
   cp docker/docker-compose.cpu.example docker-compose.yml
   cp config.yml.example config.yml
   cp .env.example .env
   ```
2. Generate a secure `SECRET_KEY` in `.env`:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
3. Verify `model.device: cpu` in `config.yml`.
4. Start the stack:
   ```bash
   docker compose up -d --build
   ```

---

### GPU Deployment (NVIDIA CUDA)

Requires an NVIDIA GPU with the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html).

1. Copy the GPU compose template and initial configuration:
   ```bash
   cp docker/docker-compose.gpu.example docker-compose.yml
   cp config.yml.example config.yml
   cp .env.example .env
   ```
2. Set `model.device: cuda` in `config.yml`.
3. Start the stack:
   ```bash
   docker compose up -d --build
   ```

---

## Pulling Updates from GitHub

When a new ScanScribe release is published, update your container stack with two simple commands:

```bash
git pull origin main
docker compose up -d --build
```

The multi-stage build will recompile any React frontend updates, and the container entrypoint will automatically apply any new Alembic database migrations on startup.

---

## Useful Docker Commands

- **View Live Logs:**
  ```bash
  docker compose logs -f scanscribe
  ```
- **Run ScanScribe CLI inside container:**
  ```bash
  docker compose exec scanscribe scanscribe --help
  docker compose exec scanscribe scanscribe status
  ```
- **Restart Container:**
  ```bash
  docker compose restart scanscribe
  ```
- **Stop Stack:**
  ```bash
  docker compose down
  ```
