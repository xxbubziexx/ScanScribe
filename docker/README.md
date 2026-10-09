# ScanScribe Docker Deployment

While ScanScribe is optimized to run as a fast, native application with its own isolated virtual environment and CLI, Docker files are maintained here for homelab, TrueNAS, and Unraid environments.

---

## CPU Deployment

1. Copy the CPU compose and requirements files to the project root:
   ```bash
   cp docker/docker-compose.cpu.example docker-compose.yml
   cp docker/requirements.cpu.example requirements.txt
   cp .env.example .env
   cp config.yml.example config.yml
   ```
2. Generate a `SECRET_KEY` in `.env`:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
3. Set `model.device: cpu` in `config.yml`.
4. Ensure the named storage volume exists:
   ```bash
   docker volume create scanscribe_audio_storage
   ```
5. Start the stack:
   ```bash
   docker compose up -d --build
   ```

---

## GPU Deployment (NVIDIA CUDA)

Requires an NVIDIA GPU with the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html).

1. Copy the GPU compose and requirements files:
   ```bash
   cp docker/docker-compose.gpu.example docker-compose.yml
   cp docker/requirements.gpu.example requirements.txt
   cp .env.example .env
   cp config.yml.example config.yml
   ```
2. Set `model.device: cuda` in `config.yml`.
3. Create the external volume:
   ```bash
   docker volume create scanscribe_audio_storage
   ```
4. Build and start:
   ```bash
   docker compose up -d --build
   ```
