#!/usr/bin/env python3
"""
ScanScribe — First-Time Interactive Setup Wizard
Cross-platform (Linux, Windows, macOS). Uses Python standard library only.
"""

import argparse
import os
import platform
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

# Colors for terminal output
class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

# Disable colors on Windows cmd if ANSI not supported
if platform.system() == "Windows" and "WT_SESSION" not in os.environ and "TERM" not in os.environ:
    for attr in dir(Colors):
        if not attr.startswith("__"):
            setattr(Colors, attr, "")

def print_banner():
    banner = f"""{Colors.CYAN}{Colors.BOLD}
======================================================================
     ____                   ____            _ _be 
    / ___|  ___ __ _ _ __  / ___|  ___ _ __(_) |__   ___ 
    \\___ \\ / __/ _` | '_ \\ \\___ \\ / __| '__| | '_ \\ / _ \\
     ___) | (_| (_| | | | | ___) | (__| |  | | |_) |  __/
    |____/ \\___\\__,_|_| |_||____/ \\___|_|  |_|_.__/ \\___|
======================================================================{Colors.RESET}
{Colors.BOLD}          AI Public Safety Radio Scanner & Transcription{Colors.RESET}
{Colors.DIM}                   First-Time Setup Wizard{Colors.RESET}
"""
    print(banner)

def ask(prompt: str, default: str = "") -> str:
    """Prompt the user for input with an optional default value."""
    if default:
        res = input(f"{Colors.BOLD}{prompt}{Colors.RESET} [{Colors.GREEN}{default}{Colors.RESET}]: ").strip()
        return res if res else default
    return input(f"{Colors.BOLD}{prompt}{Colors.RESET}: ").strip()

def ask_choice(prompt: str, options: list[tuple[str, str]], default_idx: int = 0) -> str:
    """Prompt the user to select from a list of options."""
    print(f"\n{Colors.BOLD}{prompt}{Colors.RESET}")
    for i, (key, desc) in enumerate(options, 1):
        def_marker = f" {Colors.CYAN}(default){Colors.RESET}" if i - 1 == default_idx else ""
        print(f"  [{Colors.BOLD}{i}{Colors.RESET}] {Colors.BOLD}{key}{Colors.RESET}: {desc}{def_marker}")
    
    while True:
        choice = input(f"Enter selection (1-{len(options)}) [{default_idx + 1}]: ").strip()
        if not choice:
            return options[default_idx][0]
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return options[int(choice) - 1][0]
        print(f"{Colors.RED}Invalid choice. Please enter a number between 1 and {len(options)}.{Colors.RESET}")

def ask_yes_no(prompt: str, default: bool = True) -> bool:
    """Prompt for a yes/no question."""
    def_str = "Y/n" if default else "y/N"
    res = input(f"{Colors.BOLD}{prompt}{Colors.RESET} [{def_str}]: ").strip().lower()
    if not res:
        return default
    return res in ("y", "yes")

def check_command(cmd: str) -> bool:
    """Check if an executable is found in PATH."""
    return shutil.which(cmd) is not None

def detect_gpu() -> bool:
    """Check if NVIDIA GPU is accessible."""
    if not check_command("nvidia-smi"):
        return False
    try:
        res = subprocess.run(["nvidia-smi"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return res.returncode == 0
    except Exception:
        return False

def main():
    parser = argparse.ArgumentParser(description="ScanScribe First-Time Setup Wizard")
    parser.add_argument("--cpu", action="store_true", help="Force CPU mode")
    parser.add_argument("--gpu", action="store_true", help="Force GPU mode")
    parser.add_argument("--yes", "-y", action="store_true", help="Accept all defaults without interactive prompts")
    parser.add_argument("--start", action="store_true", help="Automatically build and start docker containers after setup")
    args = parser.parse_args()

    print_banner()

    root_dir = Path(__file__).resolve().parent

    # 1. System Pre-flight Checks
    print(f"{Colors.CYAN}--- Step 1: Pre-flight Environment Checks ---{Colors.RESET}")
    has_docker = check_command("docker")
    if has_docker:
        print(f"  {Colors.GREEN}✓{Colors.RESET} Docker installed")
    else:
        print(f"  {Colors.RED}✗ Docker not found in PATH!{Colors.RESET}")
        print(f"    Please install Docker Desktop: https://www.docker.com/products/docker-desktop/")
        if not args.yes:
            if not ask_yes_no("Continue setup anyway?", default=False):
                sys.exit(1)

    has_gpu = detect_gpu()
    if has_gpu:
        print(f"  {Colors.GREEN}✓{Colors.RESET} NVIDIA GPU detected (CUDA acceleration supported)")
    else:
        print(f"  {Colors.YELLOW}ℹ{Colors.RESET} No NVIDIA GPU detected (or nvidia-smi not available). Standard CPU mode is recommended.")

    # 2. Hardware Acceleration Selection
    print(f"\n{Colors.CYAN}--- Step 2: Runtime Acceleration Mode ---{Colors.RESET}")
    if args.cpu:
        mode = "cpu"
    elif args.gpu:
        mode = "gpu"
    elif args.yes:
        mode = "gpu" if has_gpu else "cpu"
    else:
        default_idx = 1 if has_gpu else 0
        mode_choice = ask_choice(
            "Select how you want to run ScanScribe:",
            [
                ("cpu", "Standard CPU mode (Intel/AMD CPUs, no GPU needed)"),
                ("gpu", "NVIDIA GPU mode (Requires NVIDIA Container Toolkit & CUDA)"),
            ],
            default_idx=default_idx
        )
        mode = mode_choice

    print(f"Selected mode: {Colors.BOLD}{mode.upper()}{Colors.RESET}")

    # Copy docker-compose and requirements files based on mode
    docker_src = root_dir / f"docker-compose.{mode}.example"
    docker_dst = root_dir / "docker-compose.yml"
    req_src = root_dir / f"requirements.{mode}.example"
    req_dst = root_dir / "requirements.txt"

    if docker_src.exists():
        shutil.copy2(docker_src, docker_dst)
        print(f"  {Colors.GREEN}✓{Colors.RESET} Configured {Colors.BOLD}docker-compose.yml{Colors.RESET} for {mode.upper()}")
    else:
        print(f"  {Colors.YELLOW}Warning: {docker_src.name} not found!{Colors.RESET}")

    if req_src.exists():
        shutil.copy2(req_src, req_dst)
        print(f"  {Colors.GREEN}✓{Colors.RESET} Configured {Colors.BOLD}requirements.txt{Colors.RESET} for {mode.upper()}")
    else:
        print(f"  {Colors.YELLOW}Warning: {req_src.name} not found!{Colors.RESET}")

    # 3. Environment File (.env) Configuration
    print(f"\n{Colors.CYAN}--- Step 3: Security & Environment Settings (.env) ---{Colors.RESET}")
    env_file = root_dir / ".env"
    env_example = root_dir / ".env.example"

    # Generate a cryptographically secure 64-char hex key
    secret_key = secrets.token_hex(32)

    # Prompt for admin credentials
    if args.yes:
        admin_pass = "admin"
        tz_name = "America/Chicago"
    else:
        admin_pass = ask("Initial Admin Password", default="admin")
        tz_name = ask("Local Timezone (e.g. America/Chicago, America/New_York, UTC)", default="America/Chicago")

    if not env_file.exists():
        if env_example.exists():
            content = env_example.read_text(encoding="utf-8")
        else:
            content = ""

        # Replace or set SECRET_KEY
        if "SECRET_KEY=" in content:
            content = re.sub(r"SECRET_KEY=.*", f"SECRET_KEY={secret_key}", content)
        else:
            content += f"\nSECRET_KEY={secret_key}\n"

        # Replace or set TZ
        if "TZ=" in content:
            content = re.sub(r"TZ=.*", f"TZ={tz_name}", content)
        else:
            content += f"\nTZ={tz_name}\n"

        # Set SCANSCRIBE_DEFAULT_ADMIN_PASSWORD
        if "SCANSCRIBE_DEFAULT_ADMIN_PASSWORD=" in content:
            content = re.sub(r"SCANSCRIBE_DEFAULT_ADMIN_PASSWORD=.*", f"SCANSCRIBE_DEFAULT_ADMIN_PASSWORD={admin_pass}", content)
        else:
            content += f"\nSCANSCRIBE_DEFAULT_ADMIN_PASSWORD={admin_pass}\n"

        env_file.write_text(content, encoding="utf-8")
        print(f"  {Colors.GREEN}✓{Colors.RESET} Created {Colors.BOLD}.env{Colors.RESET} with secure random SECRET_KEY")
    else:
        print(f"  {Colors.GREEN}✓{Colors.RESET} Existing {Colors.BOLD}.env{Colors.RESET} file found (preserved)")

    # 4. Config File (config.yml)
    print(f"\n{Colors.CYAN}--- Step 4: Application Configuration (config.yml) ---{Colors.RESET}")
    config_file = root_dir / "config.yml"
    config_example = root_dir / "config.yml.example"

    if not config_file.exists():
        if config_example.exists():
            cfg_content = config_example.read_text(encoding="utf-8")
        else:
            cfg_content = ""

        # Update model.device according to mode
        device_val = "cuda" if mode == "gpu" else "cpu"
        cfg_content = re.sub(r"device:\s*(?:cpu|cuda)", f"device: {device_val}", cfg_content)

        config_file.write_text(cfg_content, encoding="utf-8")
        print(f"  {Colors.GREEN}✓{Colors.RESET} Created {Colors.BOLD}config.yml{Colors.RESET} (device: {device_val})")
    else:
        # Update existing config.yml device if needed
        try:
            cfg_content = config_file.read_text(encoding="utf-8")
            device_val = "cuda" if mode == "gpu" else "cpu"
            updated_content = re.sub(r"(\bdevice:\s*)(?:cpu|cuda)", rf"\g<1>{device_val}", cfg_content)
            if updated_content != cfg_content:
                config_file.write_text(updated_content, encoding="utf-8")
                print(f"  {Colors.GREEN}✓{Colors.RESET} Updated {Colors.BOLD}config.yml{Colors.RESET} model.device to {device_val}")
            else:
                print(f"  {Colors.GREEN}✓{Colors.RESET} {Colors.BOLD}config.yml{Colors.RESET} is already configured")
        except Exception as e:
            print(f"  {Colors.YELLOW}Warning reading config.yml: {e}{Colors.RESET}")

    # 5. Required Storage Directories
    print(f"\n{Colors.CYAN}--- Step 5: Directory Initialization ---{Colors.RESET}")
    dirs_to_create = ["data", "logs", "audio_storage", "models"]
    for d in dirs_to_create:
        p = root_dir / d
        p.mkdir(parents=True, exist_ok=True)
        print(f"  {Colors.GREEN}✓{Colors.RESET} Directory ready: ./{d}/")

    # 6. Whisper & Model Pre-flight Check
    models_dir = root_dir / "models"
    existing_subdirs = [x for x in models_dir.iterdir() if x.is_dir() and not x.name.startswith(".")]
    if existing_subdirs:
        print(f"  {Colors.GREEN}✓{Colors.RESET} Found models in ./models/: {', '.join(x.name for x in existing_subdirs[:3])}")
    else:
        print(f"  {Colors.YELLOW}ℹ Notice: No models found inside ./models/{Colors.RESET}")
        print(f"    You can download a base Whisper model (e.g. whisper-small) from HuggingFace,")
        print(f"    or place your fine-tuned checkpoint directly into ./models/")

    # 7. Ready to Launch
    print(f"\n{Colors.GREEN}{Colors.BOLD}======================================================================{Colors.RESET}")
    print(f"{Colors.GREEN}{Colors.BOLD}               ScanScribe Setup Complete!{Colors.RESET}")
    print(f"{Colors.GREEN}{Colors.BOLD}======================================================================{Colors.RESET}")
    print(f"\nInitial Administrator Account:")
    print(f"  Username: {Colors.BOLD}admin{Colors.RESET}")
    print(f"  Password: {Colors.BOLD}{admin_pass}{Colors.RESET}")
    print(f"\nWeb Interface URL:")
    print(f"  {Colors.CYAN}http://localhost:8000{Colors.RESET}")

    should_start = args.start or (not args.yes and ask_yes_no("\nWould you like to build and start ScanScribe now with Docker Compose?", default=True))

    if should_start:
        print(f"\n{Colors.CYAN}Starting ScanScribe with Docker Compose...{Colors.RESET}\n")
        compose_cmd = ["docker", "compose", "up", "-d", "--build"]
        try:
            subprocess.run(compose_cmd, cwd=str(root_dir), check=True)
            print(f"\n{Colors.GREEN}✓ ScanScribe is running! Visit http://localhost:8000 to get started.{Colors.RESET}")
            print(f"To monitor logs: {Colors.BOLD}docker compose logs -f{Colors.RESET}")
            print(f"To stop:         {Colors.BOLD}docker compose down{Colors.RESET}")
        except subprocess.CalledProcessError as e:
            print(f"{Colors.RED}Docker Compose failed to start: {e}{Colors.RESET}")
            print(f"You can try manually by running: {Colors.BOLD}docker compose up -d --build{Colors.RESET}")
        except Exception as e:
            print(f"{Colors.RED}Failed to run docker compose: {e}{Colors.RESET}")
    else:
        print(f"\nTo launch ScanScribe later, run:")
        print(f"  {Colors.BOLD}docker compose up -d --build{Colors.RESET}")

if __name__ == "__main__":
    main()
